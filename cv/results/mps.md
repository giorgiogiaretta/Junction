# Object recognition (YOLO-World-S / mps), 50 photos
- accuracy: 24%  |  grasp-profile correct: 24%
- latency: median 0.04 s, max 0.05 s  |  failed calls: 0

| expected \ predicted | egg | stress_ball | can | other |
|---|---|---|---|---|
| egg | 0 | 14 | 0 | 6 |
| stress_ball | 0 | 9 | 0 | 13 |
| can | 0 | 0 | 3 | 5 |
| other | 0 | 0 | 0 | 0 |

Wrong: ball/ball-002.jpg->other, ball/ball-004.jpg->other, ball/ball-005.jpg->other, ball/ball-006.jpg->other, ball/ball-007.jpg->other, ball/ball-010.jpg->other, ball/ball-013.jpg->other, ball/ball-014.jpg->other, ball/ball-017.jpg->other, ball/ball-019.jpg->other, ball/ball-020.jpg->other, ball/ball-021.jpg->other, ball/ball-022.jpg->other, can/can-002.jpg->other, can/can-003.jpg->other, can/can-004.jpg->other, can/can-005.jpg->other, can/can-007.jpg->other, egg/egg-001.jpg->other, egg/egg-002.jpg->stress_ball, egg/egg-003.jpg->stress_ball, egg/egg-004.jpg->stress_ball, egg/egg-005.jpg->other, egg/egg-006.jpg->stress_ball, egg/egg-007.jpg->stress_ball, egg/egg-008.jpg->stress_ball, egg/egg-009.jpg->stress_ball, egg/egg-010.jpg->stress_ball, egg/egg-011.jpg->stress_ball, egg/egg-012.jpg->stress_ball, egg/egg-013.jpg->stress_ball, egg/egg-014.jpg->stress_ball, egg/egg-015.jpg->other, egg/egg-016.jpg->other, egg/egg-017.jpg->other, egg/egg-018.jpg->other, egg/egg-019.jpg->stress_ball, egg/egg-020.jpg->stress_ball

Unlabelled 'mix' photos (27), model's main object (not scored): {'stress_ball': 7, 'other': 10, 'egg': 5, 'can': 5}

Per-folder: {"ball": {"correct": 9, "total": 22, "accuracy": 0.4090909090909091}, "can": {"correct": 3, "total": 8, "accuracy": 0.375}, "egg": {"correct": 0, "total": 20, "accuracy": 0.0}}
