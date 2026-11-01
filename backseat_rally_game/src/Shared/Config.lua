-- Backseat Rally: Expedition. Authored game systems, not an executor script.
return {
 Version='1.3.0', AutoOpen=true, ImportedVisuals=true, ExternalAudio=false, Generation=2, WorldX=12000, LaneSpacing=1800, StudMetres=.28, Step=1/60, StateRate=12, InputRate=20,
 Climate={dryWetness=.08,rainWetness=.45,wetGripLoss=.24,windSpeed=3},
 Chunk=256, RoadStep=8, RoadWidth=28, Checkpoint=768, MaxPlayers=8,
 ReplayRate=10, ReplayPage=500, ReplayPending=4, LibrarySize=12, BestSize=8,
 Modes={
  {id='sprint',name='Rally Sprint',tag='A road with an ending',length=6144,weather='clear',xp=240},
  {id='expedition',name='Expedition',tag='Four biomes. One long drive.',length=16384,weather='clear',xp=650},
  {id='daily',name='Daily Roadbook',tag='The same new road for everyone today',length=8192,weather='dusk',xp=340},
  {id='endless',name='Endless Journey',tag='Keep going. Bank the run whenever you want.',length=0,weather='clear',xp=0},
 },
 Cars=require(script.Parent.VehicleCatalog),
 Biomes={
  {name='Pine Country',ground={.29,.36,.24},road={.39,.34,.27},accent={.88,.66,.28},trees=true},
  {name='Alpine Pass',ground={.56,.60,.57},road={.40,.43,.43},accent={.72,.86,.91},snow=true},
  {name='Red Mesa',ground={.63,.40,.25},road={.67,.51,.35},accent={.91,.67,.33},desert=true},
  {name='North Coast',ground={.40,.51,.37},road={.36,.39,.40},accent={.80,.85,.71},coast=true},
 },
 Quality={low={behind=1,ahead=4,props=2,shadows=false},medium={behind=2,ahead=5,props=5,shadows=false},high={behind=2,ahead=6,props=9,shadows=true}},
}
