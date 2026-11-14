# vision/ - table calibration, can and hand tracking from the camera

Pipeline: video + `take_NN_frames.json` (PC wall-clock per frame, written by `Rokoko/src/cam.py`) -> `data/vision/take_NN.npz`
with the can position and the hand keypoints in **metres in the table frame** (origin = centre of the marker square,
x = BL->BR, y = BL->TL, z up; square side 0.297 m), time-aligned with the Rokoko gloves through `t_wall`.

```
python Rokoko/src/cam.py --list                      # find the camera index (the Osmo shows up as a UVC webcam)
CAM=1 python Rokoko/src/take.py                      # records data/video/take_NN.mp4 + take_NN_frames.json
python -m vision.process_video data/video/take_01.mp4 --hfov <deg> --debug data/video_debug/take_01
```

Files: `markers.py` (find the 4 yellow-green tape X, order BL/TL/TR/BR, multi-frame vote, manual fallback),
`homography.py` (`TableCalib`: pixel -> metres, optional camera pose for heights, save/load; `CameraMotion` for a moving camera),
`can_track.py` (`CanTracker`), `hand_track.py` (MediaPipe wrist + index tip), `process_video.py` (CLI), tests in `tests/test_vision.py`.

## Mounting the Osmo Action 5 Pro (recommended)

* **USB webcam mode** (UVC, 1080p30, MJPG), as in `cam.py`. Fixed on a tripod/clamp: the pipeline is designed for a FIXED camera;
  any bump after the start of a take invalidates the calibration (re-take, or use `--stabilize`, see below).
* **Height ~70-90 cm above the table**, looking straight down (or tilted at most ~30 deg from vertical, from the BL-BR edge side so
  that "image bottom = BL-BR edge"). The 29.7 cm square should fill roughly a third to half of the frame; keep the whole
  reach area plus ~10 cm around the square in view, and the 4 markers never hidden by the arm/camera mount.
* **FOV: standard (not the widest / not HyperSmart)** to limit fisheye distortion; the further from the centre, the more
  distortion corrupts the metres. Turn off horizon levelling/stabilisation (RockSteady/HorizonSteady) in webcam mode: electronic
  stabilisation warps the image and breaks the homography.
* **Manual exposure, focus and white balance** (before the take, lock them): fixed shutter ~1/200 s or faster (hand motion blur
  smears the can), ISO as low as the light allows, white balance fixed (e.g. 5000 K) so the tape stays in the HSV range, focus fixed
  on the table plane (not on the hand). Avoid direct light on the tape (specular glare turns it white) and strong shadows of the arm.
* Keep the table clear of other yellow/green things (snack bags, green cans): they are the main source of false markers.
* **Distortion**: with a standard FOV the error is a few mm over the square. For better accuracy shoot a checkerboard once with
  `cv2.calibrateCamera` and pass `--intrinsics k.json` (`{"K": [[..]], "dist": [..]}`); otherwise give the horizontal FOV with `--hfov`
  (this is used for the pinhole camera pose, which corrects the height of the can; without `--hfov` positions are projected on the table
  plane and the can centre is biased by several cm when the camera is not exactly above it).
* Marker order assumes the image is seen from the BL-BR edge (BL = bottom-left corner in the image, then clockwise BL, TL, TR, BR).
  If the camera sits on another side use `--rotate 1|2|3` (quarter turns) or `--manual` and click BL, TL, TR, BR.

## Calibration

Automatic: 40 frames across the clip are scanned, the X blobs that stay at the same pixels (>= 15% of frames) are kept, and the 4
that best form a perspective-square (`squareness`: orthogonal, equal axes for some focal length) win. A can/hand covering one
marker part of the time does not matter, the vote only needs each marker visible in some frames.
`--manual` opens a window to click the 4 centres; `--points pts.json` takes them from a file; `--save-calib c.json` /
`--calib c.json` reuse one calibration for several takes of the same session (recommended: calibrate once on an empty table).
`TableCalib.corner_residual_mm()` is ~0 by construction with 4 points; real noise shows up as `spread_px` (printed by the vote).

## Output npz

`t_wall` (s, PC clock), `frame`, `can_xy[N,2]` (m, NaN when lost), `can_q` (2 measured, 1 partial/held by occlusion, 0 lost),
`can_area_cm2`, `wrist_xy[N,2,2]` / `index_xy[N,2,2]` (frame, hand slot, xy; slots are MediaPipe's Left/Right label, which is
swapped for an un-mirrored camera: treat as hand A/B), `hand_score[N,2]`, `hand_xy_wrist[N,2]` / `hand_xy_index[N,2]` (the hand nearest
the can), `hand_ok`, `cam_ok`, `calib_json`, `meta_json`. Camera latency (typically 0.1-0.3 s) is NOT compensated: measure it once with a
visible event and shift `t_wall`.

## Notes and limits

* The can is found as foreground against a per-pixel temporal median of the clip (needs the can away from each pixel >50% of the time),
  limited to the table square +10 cm. Colour alone is unsafe (the wood and an orange can have similar hue); `--can-hsv h0,s0,v0,h1,s1,v1` adds a colour
  constraint when needed. Black gloves are excluded by brightness. When the hand hides the can the last position is held for 0.5 s (`can_q`=1).
* Hand keypoints are projected on the table plane (z=0): the fingertip height is not known, so index-tip XY has a parallax error.
  MediaPipe is weak on black Rokoko gloves with sensors (about 55-60% of frames on the hand-held dev clips): use `hand_ok`.
* `--stabilize` (ORB features to the first frame) lets a hand-held or bumped camera work, tested only on the two phone dev clips; it
  drifts under strong viewpoint changes.
* Private dev videos and `data/video_debug/`, `data/vision/` are git-ignored.
