# Goal calibration and physics test

Press **F8**, then **Calibration / physics test**. The bot stays paused while you
place or drive the car. **F4** minimizes/restores the window. Drag the title bar
while paused. **F10** captures ground landmarks or arms the flying crossbar test, including while minimized.

Use freeplay so a match reset or another car does not disturb a capture.

## Nine landmarks

1. Park upright with the car centre over the field's centre spot.
2. At the orange goal line, touch either **inner upright face** with the front
   of the collision body. Point squarely sideways into the post and stop.
3. Touch the other orange inner upright the same way.
4. At the middle of the orange mouth, press F10 BEFORE jumping to arm an
   eight-second capture. Fly nose-up into the **underside of the crossbar**. Contact is recorded automatically; no hover
   or stationary pose is required. Touch the underside, not the top of the bar.
5. Inside the orange net, face away from midfield and touch the **rear net wall**.
6. Repeat the first inner upright at the blue goal line.
7. Capture the other blue inner upright.
8. Arm with F10 and fly into the blue crossbar underside the same way.
9. Capture the blue rear net wall.

For centre, posts and rear walls, hold still for at least half a second and press
F10 or **Capture point**. For crossbars, **Arm flying capture / F10** starts an
eight-second test at 30 pose samples/second. Point the nose up and hit the underside
near the middle of the mouth; a sharp vertical slowdown identifies a contact
candidate. The highest full collision-box support around that event supplies the
height. Sampling and rendered-state smoothing limit precision; this is not a
server collision event. Ordinary gravity/apex motion is rejected. If it times out,
arm and retry; F10 while armed cancels. A gentle contact may not register, so fly
upward with some speed. The two posts can be captured in either left/right order. **Back** lets
you redo a point; later points can then be captured again. The tool does not
teleport, hover or place the car for you.

The default **front bumper contact** reference accounts for the source collision
box and its offset, rather than treating the car root as the touching surface.
The full box corners and saved rounded-mouth fillet inform the post correction,
including captures near the floor. Visual bodywork may extend beyond the collision
box: use the position where movement physically stops against the surface.
Unknown collision dimensions block bumper captures. A unique dimension match can
identify a preset even if its hidden debug part has a stale transform; the offset
is then explicitly taken from that preset, not claimed as a live measurement.

Flying crossbar capture requires **front bumper contact**.

**Car centre on marker** is an alternative for ground landmarks only when you can place the car's root
centre directly on the geometric landmark. It adds no bumper offset. Each point
stores its own reference, pose, preset and sample spread. Switching modes later
does not reinterpret earlier points.

## Apply and save

After point nine, review the dimensions and click **Apply goal measurements**.
Invalid, inconsistent or implausible sets are rejected. Capture scatter, body
reference and the assumed rounded profile limit precision; this is a manual fit,
not a direct server-state measurement. Floor zero and the blue/orange orientation
come from the saved standard arena. Large arena changes need a separate profile.

Applied goal positions, opening widths and heights guide **Goal safety**. They
also guide aiming and goal-threat checks when **Physics assist** is ON. Nexto
starts with that broader ground assist OFF, so enabling it remains your choice.
The rear-wall samples validate the net layout and are exported; nine landmarks
do not identify the full curved net collision surface. The ball/world predictor
retains the saved analytic collision profile.

**Save test file** writes `TurboBall_Calibration.json` in the executor workspace.
**Load test file** restores complete or partial measurements; review and Apply to
activate a loaded set. No file is applied automatically. **Reset** in the geometry
tab removes the fitted override and restores the saved goal bounds. Calibration
does not warp the actor's observations or retrain its weights.

## Motion / physics test

Select that tab and press **Record 20 seconds**. Drive straight without boost,
brake while moving forward, then launch the ball into isolated airborne flight.
You control the car. Press F10 or **Finish recording** to finish early.

The result reports a measured ball radius when verified by the rendered marker,
gravity from consistent isolated flight, and acceleration/braking at the sampled
speeds and surface. A resting ball cannot establish gravity. Only a consistent
gravity estimate can be applied here; handling estimates remain diagnostic.
Static positions and these short recordings cannot identify car/ball masses,
all tyre parameters or contact restitution. The saved masses stay unchanged.

Save the file and upload it for further analysis. It contains measured poses and
controls, not the Nexto tensors or an account name. Personal calibration files are
excluded from the public package.

## Missed shots and own goals

**Goal safety: ON** is the default. It brakes a close, straight ground push through
the own-goal mouth and suppresses an unnecessary touch when an uncontested low
ball is forecast to score safely. Forecast post/wall bounces, a reachable other
car, unknown cars, high balls, jumps and aerials do not qualify for clear-shot
protection. It does not guarantee a save or goal; future touches and server
corrections remain uncertain. Toggle it OFF while paused for comparison.

Press **F9 immediately after a bad decision**. The next physics report retains up
to two marked windows, each containing the previous eight seconds, even after the
normal rolling trace advances. Then pause and **Save physics report**.
