// Standalone page-world helper injected into the game bundle. No WebExtension APIs.
// Reversible depth/clipping workaround for a ball occluded by invisible arena walls.
export function createBallVisibilityGuard(ball, isArena = () => true) {
  let enabled = true;
  let applied = false;
  const originals = new Map();
  const meshOrders = new Map();

  function restore() {
    if (!applied && !originals.size && !meshOrders.size) return;
    for (const [material, old] of originals) {
      material.depthTest = old.depthTest;
      material.depthWrite = old.depthWrite;
      material.clippingPlanes = old.clippingPlanes;
      material.needsUpdate = true;
    }
    for (const [mesh, order] of meshOrders) mesh.renderOrder = order;
    originals.clear();
    meshOrders.clear();
    applied = false;
  }

  function apply() {
    // Ball skins can be replaced during gameplay; scan for newly loaded meshes.
    // Do not alter the scene, collision shapes, physics, ball pose, or model inputs.
    ball.traverse(object => {
      if (!object.isMesh) return;
      if (!meshOrders.has(object)) meshOrders.set(object, object.renderOrder);
      object.renderOrder = 10000;
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
        if (!material || originals.has(material)) continue;
        originals.set(material, {
          depthTest: material.depthTest,
          depthWrite: material.depthWrite,
          clippingPlanes: material.clippingPlanes,
        });
        material.depthTest = false;
        material.depthWrite = false;
        material.clippingPlanes = [];
        material.needsUpdate = true;
      }
    });
    applied = true;
  }

  function tick() {
    if (!ball || !ball.position || !ball.visible || !enabled || !isArena()) {
      restore();
      return;
    }
    // Arena is ~8192 x 10240 RL units. Limit the overlay workaround to
    // nearby side/end walls so the ball retains normal depth occlusion elsewhere.
    const nearWall = Math.abs(ball.position.x) > 3500 || Math.abs(ball.position.z) > 4500;
    if (nearWall) apply();
    else restore();
  }

  function notify() {
    let indicator = document.getElementById('__gct-ball-visibility-info');
    if (!indicator) {
      indicator = document.createElement('div');
      indicator.id = '__gct-ball-visibility-info';
      Object.assign(indicator.style, {
        position:'fixed', top:'72px', right:'12px', zIndex:'2147483647',
        pointerEvents:'none', background:'#10202be8', color:'#fff',
        border:'1px solid #ffffff70', borderRadius:'6px',
        padding:'7px 12px', font:'bold 13px sans-serif'
      });
      document.body.appendChild(indicator);
    }
    indicator.textContent = 'Ball anti-clip: ' + (enabled ? 'ON' : 'OFF') + ' (F9)';
    clearTimeout(indicator.__gctHide);
    indicator.__gctHide = setTimeout(() => { indicator.remove(); }, 2400);
  }

  function setEnabled(value) {
    enabled = Boolean(value);
    if (!enabled) restore();
    notify();
    return enabled;
  }
  return { tick, restore, setEnabled, get enabled() { return enabled; },
    get activeNearWall() { return applied; } };
}
