import json
import math
import os
import uuid
from typing import List, Set, FrozenSet
from datetime import timezone

from contracts.schema import DetectionResult, DetectedObject

class SuspiciousActivityDetector:
    def __init__(self, 
                 time_threshold=4.0, 
                 distance_threshold=120.0, 
                 cleanup_threshold=2.0,
                 crowd_distance_threshold=200.0,
                 crowd_min_people=4,
                 speed_threshold=50.0):
        # Slightly tuned thresholds for real-time testing
        self.time_threshold = time_threshold
        self.distance_threshold = distance_threshold
        self.cleanup_threshold = cleanup_threshold
        
        self.crowd_distance_threshold = crowd_distance_threshold
        self.crowd_min_people = crowd_min_people
        self.speed_threshold = speed_threshold
        
        self.track_history = {}
        self.alerted_crowds: Set[FrozenSet[str]] = set()

    def calculate_distance(self, p1, p2) -> float:
        return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

    @staticmethod
    def _dist2(p1, p2) -> float:
        """Squared Euclidean distance — identical ordering to sqrt version
        for threshold comparisons, minus the expensive sqrt per pair."""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        return dx * dx + dy * dy

    def process(self, result: DetectionResult) -> DetectionResult:
        """Process a DetectionResult and inject suspicious activity metadata."""
        timestamp = result.timestamp_utc.timestamp()
        
        active_human_tracks = [obj for obj in result.objects if obj.object_type == "human"]

        # Filter out authorized personnel (do not apply suspicious checks to known guards)
        filtered_human_tracks = []
        for track in active_human_tracks:
            identity = track.attributes.get("identity", "Unknown")
            if identity != "Unknown":
                continue 
            filtered_human_tracks.append(track)

        # 1. INDIVIDUAL HEURISTICS (Loitering & Erratic Movement)
        for track in filtered_human_tracks:
            track_id = track.track_id
            
            # Extract centroid and velocity from tracker's attributes
            centroid = track.attributes.get("centroid")
            if not centroid:
                # Fallback to bbox center if centroid missing
                centroid = ((track.bbox[0] + track.bbox[2]) / 2, (track.bbox[1] + track.bbox[3]) / 2)
            
            vx, vy = track.attributes.get("velocity_px_per_s", (0.0, 0.0))
            speed = math.sqrt(vx**2 + vy**2)

            if track_id not in self.track_history:
                self.track_history[track_id] = {
                    'first_seen_timestamp': timestamp,
                    'initial_position': centroid,
                    'last_seen_timestamp': timestamp,
                    'activities': set()
                }
            else:
                history = self.track_history[track_id]
                history['last_seen_timestamp'] = timestamp
                
                distance_moved2 = self._dist2(history['initial_position'], centroid)

                # --- Loitering Condition ---
                # If they move outside the radius, reset the anchor point and timer.
                if distance_moved2 > self.distance_threshold * self.distance_threshold:
                    history['initial_position'] = centroid
                    history['first_seen_timestamp'] = timestamp
                    history['activities'].discard("loitering")
                
                time_elapsed = timestamp - history['first_seen_timestamp']
                if time_elapsed >= self.time_threshold:
                    history['activities'].add("loitering")
                
                # --- Erratic Movement Condition ---
                if speed > self.speed_threshold:
                    history['activities'].add("erratic_movement")
                
                if history['activities']:
                    track.attributes['activity'] = ", ".join(list(history['activities']))

        # 2. GROUP HEURISTICS (Crowd Formation)
        if len(filtered_human_tracks) >= self.crowd_min_people:
            clusters = self._find_clusters(filtered_human_tracks)
            for cluster in clusters:
                if len(cluster) >= self.crowd_min_people:
                    for member in cluster:
                        existing = member.attributes.get('activity', '')
                        if existing:
                            if "crowd_formation" not in existing:
                                member.attributes['activity'] = existing + ", crowd_formation"
                        else:
                            member.attributes['activity'] = "crowd_formation"

        # 3. CLEANUP
        self._cleanup_stale_tracks(timestamp)
            
        return result

    def _find_clusters(self, tracks: List[DetectedObject]) -> List[List[DetectedObject]]:
        clusters = []
        # Compare squared distances (same clustering result, no sqrt).
        crowd2 = self.crowd_distance_threshold * self.crowd_distance_threshold
        for track in tracks:
            c1 = track.attributes.get("centroid", ((track.bbox[0] + track.bbox[2])/2, (track.bbox[1] + track.bbox[3])/2))
            added = False
            for cluster in clusters:
                for member in cluster:
                    c2 = member.attributes.get("centroid", ((member.bbox[0] + member.bbox[2])/2, (member.bbox[1] + member.bbox[3])/2))
                    if self._dist2(c1, c2) <= crowd2:
                        cluster.append(track)
                        added = True
                        break
                if added: break
            if not added:
                clusters.append([track])
        return clusters

    def _cleanup_stale_tracks(self, current_timestamp: float):
        lost_tracks = [tid for tid, history in self.track_history.items() 
                       if current_timestamp - history['last_seen_timestamp'] > self.cleanup_threshold]
        for tid in lost_tracks:
            del self.track_history[tid]
