---
description: Every TCP command the reward server understands
---

# Protocol

Newline-delimited JSON on `127.0.0.1:<port>`, default 42069. One request object per line, one reply per line. Every reply has `"ok"`, failures add `"error"`. A line over 16 MiB closes the connection. One client at a time. The protocol version is `1`, and `hello` lists the commands the running server supports. `tests/smoke_client.py` is a minimal client.

## Reward

| cmd | request fields | reply fields |
|---|---|---|
| `hello` | | `server`, `proto`, `commands` |
| `ping` | | |
| `load` | `config` | `count`, `names` |
| `reload` | | `count`, `names` (uses the last `config`) |
| `eval` | see below | `total`, `names`, `values`, `weights`, `weighted` |
| `capture` | state fields as `eval`; `tick_skip` = ticks the tick spans (default 1) | `frames` |
| `reset` | `clear_buffer` (default false) | clears episode state, and with `clear_buffer` the clip buffers |

### `eval` request

```json
{
  "cmd": "eval", "step": 0, "force_all": true, "tick_skip": 8, "focus": 0, "debug": false,
  "goal_scored": false, "last_touch_car": -1,
  "cars": [ { "...": "car fields" } ],
  "ball": { "pos": [0,0,93], "vel": [0,0,0], "ang_vel": [0,0,0], "rot_mat": [1,0,0, 0,1,0, 0,0,1] },
  "game": { "boost_pad_states": [1], "boost_pad_timers": [0.0] }
}
```

*   `force_all` (default true) evaluates at a late step so every scheduled term has full weight. Set it false to use `step`.
*   `tick_skip` is how many physics ticks the previous state advances. Default 8, minimum 1.
*   `focus` is the car whose terms are reported.
*   `boost_pad_states` and `boost_pad_timers` have 34 entries. `rot_mat` is row-major with 9.

Car fields, all optional:

| Field | Meaning |
|---|---|
| `pos`, `vel`, `ang_vel`, `rot_mat` | kinematics |
| `team` | 0 blue, 1 orange |
| `boost` | 0 to 100 |
| `is_on_ground`, `has_jumped`, `has_double_jumped`, `has_flipped`, `is_flipping`, `is_jumping`, `is_supersonic` | flags, 0 or 1 |
| `jump_time`, `flip_time`, `air_time_since_jump`, `handbrake_val` | seconds or 0 to 1 |
| `flip_rel_torque` | vector |
| `world_contact_has`, `world_contact_normal` | surface contact |
| `prev_action` | `throttle`, `steer`, `pitch`, `yaw`, `roll`, `jump`, `boost`, `handbrake` |
| `is_demoed`, `demo_respawn_timer` | demolition |
| `is_ball_touched` | the car touched the ball this tick |

## Clips

| cmd | request fields | reply fields |
|---|---|---|
| `save_clip` | `name`, `subfolder` (default `generic`), `only_focus` (ball and car 0 only), `source` (`live` or `replay`) | `path`, `frames` |
| `list_clips` | | `folder`, `clips` |
| `clip_info` | | `folder`, `window_seconds`, `buffered_frames` |
| `set_clip_window` | `seconds` (min 1) | `window_seconds` |
| `set_clip_folder` | `folder` | `folder` |
| `create_clip_folder` | `path` | |
| `rename_clip_path` | `from`, `to` | |
| `move_clip` | `source`, `folder` | |

Paths in the last three are relative to the clip folder. Absolute paths and `..` are refused.

## Shot tasks

| cmd | request fields | reply fields |
|---|---|---|
| `get_tasks` | | `active_index`, `tasks`, `tasks_path` |
| `set_active_task` | `index` | `active_index`, `tasks`, `message` |
| `log_task_attempt` | `scored` | `active_index`, `tasks`, `message`, `last_attempt` |
| `undo_task_attempt` | | same. Fails with `message: "Nothing to undo"` |
| `reset_task` | `index` (-1 for all) | `active_index`, `tasks`, `message` |
| `reload_tasks` | `path` | `active_index`, `tasks`, `tasks_path`, `message` |
| `save_task_clip` | `clip_folder`, `subfolder`, `only_focus`, `source` | `path`, `active_index`, `tasks`, `message`, `last_attempt` |

`message` is one line the overlay shows as a toast. `last_attempt` has `task`, `number`, `outcome` (`none`, `unmarked`, `scored`, `miss`) and `clip`.

`save_task_clip` counts a new attempt, unmarked. `log_task_attempt` sets its outcome. The other outcome changes it, the same one does nothing, so a wrong key never counts twice. With no attempt to mark, or 90 s after it, `log_task_attempt` logs an attempt without a clip. `undo_task_attempt` removes the latest attempt from the counters and renames its clip to `<name>_undone.rlpr`. Switching task, reloading or resetting ends the marking window.

