-- Shared, bounded settings schema. Saved values never become physics code or input instances.
local P={}
P.definitions={
 {key='quality',name='Scenery quality',section='Graphics',choices={'low','medium','high'},default='medium',help='Changes roadside detail and scenery workload.'},
 {key='autoQuality',name='Automatic quality',section='Graphics',choices={true,false},default=true,help='Allows a lower scenery preset when frames stay slow.'},
 {key='fov',name='Field of view',section='Driving',min=60,max=100,step=5,default=78,help='Cockpit view width. Driving always stays inside the car.'},
 {key='seatHeight',name='Seat height',section='Driving',min=-.5,max=.8,step=.1,default=0,help='Fine adjustment above the standard driver eye position.'},
 {key='seatForward',name='Seat position',section='Driving',min=-.8,max=.8,step=.1,default=0,help='Move your cockpit viewpoint forward or back.'},
 {key='shake',name='Camera motion',section='Driving',min=0,max=1,step=.25,default=.5,help='Body motion and impact shake strength; zero is steadier.'},
 {key='lookSensitivity',name='Look sensitivity',section='Driving',min=.25,max=2,step=.25,default=1,help='Mouse look speed inside the cockpit.'},
 {key='assists',name='Keyboard assists',section='Driving',choices={true,false},default=true,help='Smooths digital steering and supports traction and braking.'},
 {key='damage',name='Mechanical damage',section='Driving',choices={true,false},default=true,help='Applies tyre and mechanical consequences to your car.'},
 {key='crashEffects',name='Impact screen effect',section='Driving',choices={'off','red','blackout'},default='red',help='Optional red flash or severe-impact blackout; never graphic.'},
 {key='tyrePressure',name='Cold tyre pressure',section='Driving',min=.7,max=1.3,step=.05,default=1,help='Relative pressure: 1.00 is the car default. Applies during service.'},
}
P.actions={
 {id='throttle',name='Accelerate',key='W'},{id='brake',name='Brake',key='S'},
 {id='left',name='Steer left',key='A'},{id='right',name='Steer right',key='D'},
 {id='handbrake',name='Handbrake',key='Space'},{id='reverse',name='Reverse',key='Down'},
 {id='recover',name='Recover to checkpoint',key='R'},{id='service',name='Service / replace tyres',key='T'},
 {id='bookmark',name='Mark replay moment',key='B'},{id='camera',name='Replay camera / cockpit look',key='C'},
 {id='callLeft',name='Co-driver: left',key='J'},{id='callRight',name='Co-driver: right',key='K'},
 {id='caution',name='Co-driver: caution',key='L'},{id='headlights',name='Headlights',key='H'},
 {id='settings',name='Open settings',key='F4'},
}
local byKey,byAction={},{}
for _,d in ipairs(P.definitions)do byKey[d.key]=d end
for _,a in ipairs(P.actions)do byAction[a.id]=a end
local function copy(t)local out={};for k,v in pairs(t)do out[k]=v end;return out end
function P.defaults()
 local values,bindings={},{}
 for _,d in ipairs(P.definitions)do values[d.key]=d.default end
 for _,a in ipairs(P.actions)do bindings[a.id]=a.key end
 return {values=values,bindings=bindings}
end
function P.value(key,value)
 local d=byKey[key];if not d then return nil end
 if d.choices then if table.find(d.choices,value)then return value end;return d.default end
 if type(value)~='number'or value~=value or value==math.huge or value==-math.huge then return d.default end
 local n=math.clamp(value,d.min,d.max)
 return math.clamp(math.floor((n-d.min)/d.step+.5)*d.step+d.min,d.min,d.max)
end
local keyNames={}
for name in ('A B C D E F G H I J K L M N O P Q R S T U V W X Y Z Zero One Two Three Four Five Six Seven Eight Nine F1 F2 F3 F4 F5 F6 F7 F8 F9 F10 F11 F12 Space Tab Return Backspace Insert Delete Home End PageUp PageDown Up Down Left Right LeftShift RightShift LeftControl RightControl LeftAlt RightAlt Minus Equals LeftBracket RightBracket BackSlash Semicolon Quote Backquote Comma Period Slash CapsLock NumLock ScrollLock KeypadZero KeypadOne KeypadTwo KeypadThree KeypadFour KeypadFive KeypadSix KeypadSeven KeypadEight KeypadNine KeypadPeriod KeypadDivide KeypadMultiply KeypadMinus KeypadPlus KeypadEnter KeypadEquals'):gmatch('%S+')do keyNames[name]=true end
function P.validKey(key)
 -- Explicit keyboard enum allowlist also bounds server-side saved bindings.
 return type(key)=='string'and keyNames[key]==true
end
function P.rebind(bindings,action,key)
 if not byAction[action]or not P.validKey(key)then return false end
 local previous=bindings[action]
 for other,value in pairs(bindings)do if other~=action and value==key then bindings[other]=previous end end
 bindings[action]=key;return true
end
function P.normalize(snapshot)
 local out=P.defaults();snapshot=type(snapshot)=='table'and snapshot or {}
 local values=type(snapshot.values)=='table'and snapshot.values or {}
 for _,d in ipairs(P.definitions)do if values[d.key]~=nil then out.values[d.key]=P.value(d.key,values[d.key])end end
 local bindings=type(snapshot.bindings)=='table'and snapshot.bindings or {}
 -- Swaps preserve one accessible key per action even with malformed duplicate input.
 for _,a in ipairs(P.actions)do if P.validKey(bindings[a.id])then P.rebind(out.bindings,a.id,bindings[a.id])end end
 return out
end
P.sanitize=P.normalize
function P.keyMap(bindings)
 local out={};for _,a in ipairs(P.actions)do out[bindings[a.id]]=a.id end;return out
end
function P.copy(snapshot)return {values=copy(snapshot.values),bindings=copy(snapshot.bindings)}end
return P
