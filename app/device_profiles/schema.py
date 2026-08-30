REQUIRED_PROFILE_KEYS={"code","display_name","device_type","asset_type","transport","firmware_family","capabilities","channels","output_channels"}
REQUIRED_CHANNEL_KEYS={"key","label","signal_type","source_type","unit","widget","direction"}
VALID_DIRECTIONS={"INPUT","OUTPUT","HEALTH","LOCATION"}

def analog_channel(key,label,source_type,unit="%",raw_min=0.0,raw_max=100.0,eng_min=0.0,eng_max=100.0):
 return {"key":key,"label":label,"signal_type":"CUSTOM","source_type":source_type,"unit":unit,"widget":"numeric","direction":"INPUT","calibratable":True,"defaults":{"calibration_mode":"LINEAR","raw_min":raw_min,"raw_max":raw_max,"eng_min":eng_min,"eng_max":eng_max,"offset":0.0,"filter_alpha":1.0,"deadband":0.0,"critical_low":None,"warning_low":None,"warning_high":None,"critical_high":None}}

def input_channel(key,label,signal_type,source_type,unit="",widget="status"):
 return {"key":key,"label":label,"signal_type":signal_type,"source_type":source_type,"unit":unit,"widget":widget,"direction":"INPUT","calibratable":False}

def output_feedback(key,label,source_type,channel):
 return {"key":key,"label":label,"signal_type":"STATE","source_type":source_type,"unit":"","widget":"status","direction":"OUTPUT","calibratable":False,"command_channel":channel}

def health_channel(key,label,signal_type,source_type,unit="",widget="status"):
 return {"key":key,"label":label,"signal_type":signal_type,"source_type":source_type,"unit":unit,"widget":widget,"direction":"HEALTH","calibratable":False}

def validate_profile(profile):
 missing=REQUIRED_PROFILE_KEYS-set(profile);errors=[]
 if missing:errors.append("missing profile keys: "+", ".join(sorted(missing)))
 keys=set();outputs={x.get("channel") for x in profile.get("output_channels",[])}
 for channel in profile.get("channels",[]):
  absent=REQUIRED_CHANNEL_KEYS-set(channel)
  if absent:errors.append(f"{channel.get('key','?')}: missing {sorted(absent)}")
  if channel.get("direction") not in VALID_DIRECTIONS:errors.append(f"{channel.get('key','?')}: invalid direction")
  if channel.get("key") in keys:errors.append(f"duplicate channel key: {channel.get('key')}")
  keys.add(channel.get("key"))
  if channel.get("command_channel") and channel.get("command_channel") not in outputs:errors.append(f"{channel.get('key')}: command channel is not declared")
  if channel.get("calibratable") and channel.get("direction")!="INPUT":errors.append(f"{channel.get('key')}: only INPUT may be calibratable")
 for reserved in profile.get("reserved_pins",[]):
  if reserved.get("customer_output") is not False:errors.append(f"reserved pin {reserved.get('pin')} must not be a customer output")
 if errors:raise ValueError(profile.get("code","UNKNOWN")+": "+"; ".join(errors))
 return profile
