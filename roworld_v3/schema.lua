-- Versioned RoWorld features. No OpenFront checkpoint is compatible with this schema.
local Schema = {
    version = 'roworld-observation-v1', context = 204, action = 48, hidden = 32,
    max_candidates = 96, prior_scale = 1, decision_ticks = 10,
    types = {'wait','spawn','expand','attack','boat','retreat','city','factory','port',
        'defense','sam','silo','warship','move_warship','ally_request','ally_accept',
        'ally_reject','ally_extend','donate','atom','hydrogen','mirv','ally_break'},
}
Schema.ids = {}
for i,name in ipairs(Schema.types) do Schema.ids[name]=i end
Schema.globals = {'phase_spawn','phase_play','match_minutes','home_log','capacity_log',
    'home_fraction','gold_log','land_fraction','income_log','incoming_ratio','committed_ratio',
    'reserve_ratio','available_ratio','neutral_front_log','foreign_fronts','human_fronts',
    'strongest_neighbor_ratio','city_levels','factory_levels','port_levels','posts','sams',
    'silos','ships','transports','missile_alerts','own_team','team_count','nearby_allies',
    'leader_land_ratio','own_traitor','front_scan_coverage'}
Schema.arguments = {'troop_fraction','cost_fraction','target_home_ratio','target_land_ratio',
    'target_gold_log','target_human','target_country','target_tribe','actual_ally','protected_friend',
    'incoming_from_target','pressure_on_target','already_committed_to_target','useful_assets',
    'target_ally_army_ratio','distance_to_core','flatness','coastal','fallout','upgrade','level',
    'quantity_needed_ratio','threat_exposure','estimated_payback','policy_prior'}
function Schema.clamp(x,lo,hi)
    if type(x)~='number' or x~=x or math.abs(x)==math.huge then return 0 end
    return math.clamp(x,lo or -8,hi or 8)
end
function Schema.log(x) return math.log(1+math.max(0,x or 0))/16 end
return Schema
