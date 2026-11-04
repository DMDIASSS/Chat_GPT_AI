"""Camera-only patch for VirxEC/rlviser a4e524085cdb1601cf9c0af2f815591fb696db54 (MIT)."""
from pathlib import Path
import sys


def replace(text,old,new):
    if text.count(old)!=1: raise ValueError('Pinned RLViser source did not match: '+old[:100])
    return text.replace(old,new)


def patch(root):
    root=Path(root)
    path=root/'src/settings/options.rs';text=path.read_text()
    text=replace(text,'    pub ball_cam: bool,','    pub ball_cam: bool,\n    pub camera_fov: f32,\n    pub camera_distance: f32,\n    pub camera_height: f32,\n    pub camera_pitch: f32,')
    text=replace(text,'            ball_cam: true,','            ball_cam: true,\n            camera_fov: 110.,\n            camera_distance: 270.,\n            camera_height: 100.,\n            camera_pitch: -4.,')
    text=replace(text,'camera_state: PrimaryCamera::Spectator,','camera_state: PrimaryCamera::TrackCar(1),')
    text=replace(text,'.insert_resource(MenuFocused::default())','.insert_resource(MenuFocused(false))')
    text=replace(text,'                "ball_cam" => options.ball_cam = value.parse().unwrap(),',
        '                "ball_cam" => options.ball_cam = value.parse().unwrap(),\n'+
        '\n'.join(f'                "{key}" => options.{key} = value.parse().unwrap(),' for key in ['camera_fov','camera_distance','camera_height','camera_pitch']))
    text=replace(text,'        file.write_fmt(format_args!("ball_cam={}\\n", self.ball_cam))?;',
        '        file.write_fmt(format_args!("ball_cam={}\\n", self.ball_cam))?;\n'+
        '\n'.join(f'        file.write_fmt(format_args!("{key}={{}}\\n", self.{key}))?;' for key in ['camera_fov','camera_distance','camera_height','camera_pitch']))
    text=replace(text,'            || self.ball_cam != other.ball_cam',
        '            || self.ball_cam != other.ball_cam\n'+
        '\n'.join(f'            || self.{key} != other.{key}' for key in ['camera_fov','camera_distance','camera_height','camera_pitch']))
    path.write_text(text)
    path=root/'src/camera.rs';text=path.read_text()
    marker='pub struct CameraPlugin;'
    helper='''// NovaForge: Rocket League-style horizontal FOV, adapted to the current aspect ratio.
fn update_camera_lens(options: Res<crate::settings::options::Options>, mut cameras: Query<&mut Projection, With<PrimaryCamera>>) {
    for mut projection in &mut cameras {
        if let Projection::Perspective(p) = projection.as_mut() {
            let horizontal = options.camera_fov.clamp(30., 140.).to_radians();
            p.fov = 2. * ((horizontal / 2.).tan() / p.aspect_ratio.max(0.1)).atan();
        }
    }
}

'''
    text=replace(text,marker,helper+marker)
    text=replace(text,'.add_systems(Update, daylight_cycle);','.add_systems(Update, (daylight_cycle, update_camera_lens));')
    path.write_text(text)
    path=root/'src/udp.rs';text=path.read_text()
    text=replace(text,'    ballcam: Res<BallCam>,','    ballcam: Res<BallCam>,\n    options: Res<Options>,')
    old='''        camera_transform.translation = car_transform.translation + (car_transform.translation - ball_pos).normalize() * 300.;
        camera_transform.look_at(ball_pos, Vec3::Y);
        camera_transform.translation += camera_transform.up() * 150.;
        camera_transform.look_at(ball_pos, Vec3::Y);
        camera_transform.translation.y = camera_transform.translation.y.max(MIN_CAMERA_BALLCAM_HEIGHT);'''
    new='''        // NovaForge preset: fixed car-relative boom and world-up; no artificial camera shake.
        let delta = ball_pos - car_transform.translation;
        let forward = car_transform.forward();
        let fallback = Vec3::new(forward.x, 0., forward.z).try_normalize().unwrap_or(Vec3::Z);
        let direction = Vec3::new(delta.x, 0., delta.z).try_normalize().unwrap_or(fallback);
        camera_transform.translation = car_transform.translation
            - direction * options.camera_distance.clamp(50., 1000.)
            + Vec3::Y * options.camera_height.clamp(20., 500.);
        camera_transform.translation.y = camera_transform.translation.y.max(MIN_CAMERA_BALLCAM_HEIGHT);
        camera_transform.look_at(ball_pos, Vec3::Y);
        camera_transform.rotation *= Quat::from_rotation_x(options.camera_pitch.clamp(-45., 10.).to_radians());'''
    text=replace(text,old,new)
    text=replace(text,'car_look * 280. + Vec3::Y * 110.','car_look * options.camera_distance.clamp(50., 1000.) + Vec3::Y * options.camera_height.clamp(20., 500.).')
    text=replace(text,'Quat::from_rotation_x(-PI / 30.)','Quat::from_rotation_x(options.camera_pitch.clamp(-45., 10.).to_radians())')
    path.write_text(text)
    path=root/'src/settings/gui.rs';text=path.read_text()
    text=replace(text,'    mut last_focus: Local<bool>,','    mut last_focus: Local<bool>,\n    mut initialized: Local<bool>,')
    text=replace(text,'    if *last_focus != menu_focused.0 {','    if !*initialized || *last_focus != menu_focused.0 {\n        *initialized = true;')
    path.write_text(text)


if __name__=='__main__':
    patch(sys.argv[1])
    print('RLVISER_NOVAFORGE_CAMERA_PATCHED')
