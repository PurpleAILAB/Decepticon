// Threat-intelligence overlay for the Skillogy graph.
// Additive (MERGE-based, idempotent). Source: MITRE ATT&CK v19.1.
// Covers 22 adversary-emulation profiles, 16 malware families,
// 5 new MoC navigation categories, and ~10 COUNTERED_BY defensive edges.

// ============================================================
// === ThreatActor nodes ======================================
// ============================================================

// --- Russia ---
MERGE (ta:ThreatActor {name: 'APT28', mitre_id: 'G0007'})
SET ta.aliases = ['Fancy Bear', 'Forest Blizzard', 'Sofacy', 'STRONTIUM', 'Sednit', 'Pawn Storm', 'Tsar Team', 'GruesomeLarch', 'IRON TWILIGHT'],
    ta.attribution = 'Russia (GRU Unit 26165)',
    ta.motivation = 'Espionage',
    ta.active_since = '2004';

MERGE (ta:ThreatActor {name: 'APT29', mitre_id: 'G0016'})
SET ta.aliases = ['Cozy Bear', 'Midnight Blizzard', 'NOBELIUM', 'The Dukes', 'YTTRIUM', 'IRON RITUAL', 'Dark Halo', 'UNC2452'],
    ta.attribution = 'Russia (SVR)',
    ta.motivation = 'Espionage',
    ta.active_since = '2008';

MERGE (ta:ThreatActor {name: 'Sandworm', mitre_id: 'G0034'})
SET ta.aliases = ['Sandworm Team', 'Voodoo Bear', 'Seashell Blizzard', 'ELECTRUM', 'Telebots', 'IRON VIKING', 'IRIDIUM', 'APT44'],
    ta.attribution = 'Russia (GRU Unit 74455)',
    ta.motivation = 'Sabotage, Espionage',
    ta.active_since = '2009';

MERGE (ta:ThreatActor {name: 'Turla', mitre_id: 'G0010'})
SET ta.aliases = ['Snake', 'Venomous Bear', 'Secret Blizzard', 'IRON HUNTER', 'Waterbug', 'Krypton', 'BELUGASTURGEON'],
    ta.attribution = 'Russia (FSB Center 16)',
    ta.motivation = 'Espionage',
    ta.active_since = '2004';

// --- China ---
MERGE (ta:ThreatActor {name: 'APT41', mitre_id: 'G0096'})
SET ta.aliases = ['Double Dragon', 'Wicked Panda', 'Winnti', 'BARIUM', 'Brass Typhoon'],
    ta.attribution = 'China (MSS / Chengdu 404)',
    ta.motivation = 'Espionage, Financial',
    ta.active_since = '2012';

MERGE (ta:ThreatActor {name: 'Volt Typhoon', mitre_id: 'G1017'})
SET ta.aliases = ['BRONZE SILHOUETTE', 'Vanguard Panda', 'Insidious Taurus', 'Voltzite', 'DEV-0391'],
    ta.attribution = 'China (PRC / PLA)',
    ta.motivation = 'Pre-positioning, Critical Infrastructure',
    ta.active_since = '2021';

MERGE (ta:ThreatActor {name: 'Salt Typhoon', mitre_id: 'G1045'})
SET ta.aliases = ['GhostEmperor', 'FamousSparrow', 'Earth Estries', 'UNC2286'],
    ta.attribution = 'China (MSS)',
    ta.motivation = 'Espionage, Telecommunications',
    ta.active_since = '2019';

MERGE (ta:ThreatActor {name: 'Mustang Panda', mitre_id: 'G0129'})
SET ta.aliases = ['BRONZE PRESIDENT', 'STATELY TAURUS', 'RedDelta', 'TA416', 'Earth Preta', 'CAMARO DRAGON', 'Twill Typhoon'],
    ta.attribution = 'China (MSS)',
    ta.motivation = 'Espionage',
    ta.active_since = '2012';

MERGE (ta:ThreatActor {name: 'APT10', mitre_id: 'G0045'})
SET ta.aliases = ['Stone Panda', 'MenuPass', 'POTASSIUM', 'Red Apollo', 'CVNX', 'Cicada', 'Earth Tengshe'],
    ta.attribution = 'China (MSS / Tianjin Bureau)',
    ta.motivation = 'Espionage',
    ta.active_since = '2006';

// --- Iran ---
MERGE (ta:ThreatActor {name: 'APT33', mitre_id: 'G0064'})
SET ta.aliases = ['Elfin', 'Peach Sandstorm', 'HOLMIUM', 'MAGNALLIUM', 'Refined Kitten'],
    ta.attribution = 'Iran (IRGC)',
    ta.motivation = 'Espionage, Destructive',
    ta.active_since = '2013';

MERGE (ta:ThreatActor {name: 'APT34', mitre_id: 'G0049'})
SET ta.aliases = ['OilRig', 'Helix Kitten', 'Hazel Sandstorm', 'EUROPIUM', 'Crambus', 'Earth Simnavaz'],
    ta.attribution = 'Iran (MOIS)',
    ta.motivation = 'Espionage',
    ta.active_since = '2014';

MERGE (ta:ThreatActor {name: 'MuddyWater', mitre_id: 'G0069'})
SET ta.aliases = ['MERCURY', 'Mango Sandstorm', 'Static Kitten', 'Seedworm', 'TEMP.Zagros', 'Earth Vetala'],
    ta.attribution = 'Iran (MOIS)',
    ta.motivation = 'Espionage',
    ta.active_since = '2017';

MERGE (ta:ThreatActor {name: 'Pink Sandstorm', mitre_id: 'G1030'})
SET ta.aliases = ['Agrius', 'AMERICIUM', 'DEV-0227', 'BlackShadow'],
    ta.attribution = 'Iran (IRGC)',
    ta.motivation = 'Destructive, Espionage',
    ta.active_since = '2020';

// --- North Korea ---
MERGE (ta:ThreatActor {name: 'Lazarus', mitre_id: 'G0032'})
SET ta.aliases = ['Lazarus Group', 'Hidden Cobra', 'Diamond Sleet', 'Labyrinth Chollima', 'ZINC', 'NICKEL ACADEMY', 'BlueNoroff', 'Andariel'],
    ta.attribution = 'North Korea (RGB)',
    ta.motivation = 'Financial, Espionage, Sabotage',
    ta.active_since = '2009';

MERGE (ta:ThreatActor {name: 'APT37', mitre_id: 'G0067'})
SET ta.aliases = ['Reaper', 'ScarCruft', 'Ricochet Chollima', 'InkySquid', 'Group123', 'TEMP.Reaper'],
    ta.attribution = 'North Korea (MSS)',
    ta.motivation = 'Espionage',
    ta.active_since = '2012';

MERGE (ta:ThreatActor {name: 'Kimsuky', mitre_id: 'G0094'})
SET ta.aliases = ['Velvet Chollima', 'Emerald Sleet', 'THALLIUM', 'Black Banshee', 'APT43', 'Springtail'],
    ta.attribution = 'North Korea (RGB)',
    ta.motivation = 'Espionage, Credential Theft',
    ta.active_since = '2012';

// --- South Asia ---
MERGE (ta:ThreatActor {name: 'APT36', mitre_id: 'G0134'})
SET ta.aliases = ['Transparent Tribe', 'Mythic Leopard', 'ProjectM', 'Earth Karkaddan', 'Copper Fieldstone'],
    ta.attribution = 'Pakistan (ISI)',
    ta.motivation = 'Espionage',
    ta.active_since = '2013';

MERGE (ta:ThreatActor {name: 'Patchwork', mitre_id: 'G0040'})
SET ta.aliases = ['Dropping Elephant', 'Chinastrats', 'MONSOON', 'Operation Hangover', 'Zinc Emerson'],
    ta.attribution = 'India',
    ta.motivation = 'Espionage',
    ta.active_since = '2015';

MERGE (ta:ThreatActor {name: 'SideWinder', mitre_id: 'G0121'})
SET ta.aliases = ['Rattlesnake', 'T-APT-04', 'Razor Tiger', 'Hardcore Nationalist'],
    ta.attribution = 'India',
    ta.motivation = 'Espionage',
    ta.active_since = '2012';

// --- Financial / Cybercrime ---
MERGE (ta:ThreatActor {name: 'FIN7', mitre_id: 'G0046'})
SET ta.aliases = ['Carbanak', 'Carbon Spider', 'Sangria Tempest', 'GOLD NIAGARA', 'ELBRUS', 'ITG14'],
    ta.attribution = 'Cybercrime (Eastern Europe)',
    ta.motivation = 'Financial',
    ta.active_since = '2013';

MERGE (ta:ThreatActor {name: 'Scattered Spider', mitre_id: 'G1015'})
SET ta.aliases = ['UNC3944', 'Octo Tempest', 'Muddled Libra', 'Star Fraud', '0ktapus'],
    ta.attribution = 'Cybercrime (The Com)',
    ta.motivation = 'Financial, Extortion',
    ta.active_since = '2022';

// --- Middle East ---
MERGE (ta:ThreatActor {name: 'Dark Caracal', mitre_id: 'G0070'})
SET ta.aliases = ['Bandook Group'],
    ta.attribution = 'Lebanon (GDGS)',
    ta.motivation = 'Espionage, Surveillance',
    ta.active_since = '2012';


// ============================================================
// === ThreatActor -> Skill EMULATED_BY edges =================
// ============================================================

MATCH (ta:ThreatActor {name: 'APT28'}), (s:Skill {name: 'apt28-fancy-bear'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'APT29'}), (s:Skill {name: 'apt29-cozy-bear'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'APT33'}), (s:Skill {name: 'apt33-elfin'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'APT34'}), (s:Skill {name: 'apt34-oilrig'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'APT41'}), (s:Skill {name: 'apt41-double-dragon'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Lazarus'}), (s:Skill {name: 'lazarus-group'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'FIN7'}), (s:Skill {name: 'fin7-carbanak'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Sandworm'}), (s:Skill {name: 'sandworm-team'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Volt Typhoon'}), (s:Skill {name: 'volt-typhoon'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Scattered Spider'}), (s:Skill {name: 'scattered-spider'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Salt Typhoon'}), (s:Skill {name: 'salt-typhoon'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Turla'}), (s:Skill {name: 'turla'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'MuddyWater'}), (s:Skill {name: 'muddywater'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'APT36'}), (s:Skill {name: 'apt36-transparent-tribe'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'APT37'}), (s:Skill {name: 'apt37-reaper'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Mustang Panda'}), (s:Skill {name: 'mustang-panda'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Dark Caracal'}), (s:Skill {name: 'dark-caracal'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Patchwork'}), (s:Skill {name: 'patchwork'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Pink Sandstorm'}), (s:Skill {name: 'pink-sandstorm'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'APT10'}), (s:Skill {name: 'apt10-stone-panda'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'Kimsuky'}), (s:Skill {name: 'kimsuky'})
MERGE (ta)-[:EMULATED_BY]->(s);

MATCH (ta:ThreatActor {name: 'SideWinder'}), (s:Skill {name: 'sidewinder'})
MERGE (ta)-[:EMULATED_BY]->(s);


// ============================================================
// === ThreatActor -> Technique USES_TECHNIQUE edges ==========
// === (top 5 characteristic techniques per actor) ============
// ============================================================

// --- APT28 (G0007) ---
MATCH (ta:ThreatActor {name: 'APT28'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT28'}), (t:Technique {id: 'T1078'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT28'}), (t:Technique {id: 'T1110.003'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT28'}), (t:Technique {id: 'T1203'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT28'}), (t:Technique {id: 'T1027'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- APT29 (G0016) ---
MATCH (ta:ThreatActor {name: 'APT29'}), (t:Technique {id: 'T1078'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT29'}), (t:Technique {id: 'T1195.002'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT29'}), (t:Technique {id: 'T1550.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT29'}), (t:Technique {id: 'T1098.003'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT29'}), (t:Technique {id: 'T1114.002'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- APT33 (G0064) ---
MATCH (ta:ThreatActor {name: 'APT33'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT33'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT33'}), (t:Technique {id: 'T1003.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT33'}), (t:Technique {id: 'T1053.005'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT33'}), (t:Technique {id: 'T1110.003'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- APT34 (G0049) ---
MATCH (ta:ThreatActor {name: 'APT34'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT34'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT34'}), (t:Technique {id: 'T1071.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT34'}), (t:Technique {id: 'T1053.005'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT34'}), (t:Technique {id: 'T1105'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- APT41 (G0096) ---
MATCH (ta:ThreatActor {name: 'APT41'}), (t:Technique {id: 'T1190'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT41'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT41'}), (t:Technique {id: 'T1195.002'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT41'}), (t:Technique {id: 'T1505.003'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT41'}), (t:Technique {id: 'T1027'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Lazarus (G0032) ---
MATCH (ta:ThreatActor {name: 'Lazarus'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Lazarus'}), (t:Technique {id: 'T1059.007'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Lazarus'}), (t:Technique {id: 'T1486'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Lazarus'}), (t:Technique {id: 'T1027'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Lazarus'}), (t:Technique {id: 'T1071.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- FIN7 (G0046) ---
MATCH (ta:ThreatActor {name: 'FIN7'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'FIN7'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'FIN7'}), (t:Technique {id: 'T1059.005'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'FIN7'}), (t:Technique {id: 'T1027'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'FIN7'}), (t:Technique {id: 'T1071.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Sandworm (G0034) ---
MATCH (ta:ThreatActor {name: 'Sandworm'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Sandworm'}), (t:Technique {id: 'T1486'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Sandworm'}), (t:Technique {id: 'T1561.002'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Sandworm'}), (t:Technique {id: 'T1190'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Sandworm'}), (t:Technique {id: 'T1053.005'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Volt Typhoon (G1017) ---
MATCH (ta:ThreatActor {name: 'Volt Typhoon'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Volt Typhoon'}), (t:Technique {id: 'T1078'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Volt Typhoon'}), (t:Technique {id: 'T1046'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Volt Typhoon'}), (t:Technique {id: 'T1003.003'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Volt Typhoon'}), (t:Technique {id: 'T1562.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Scattered Spider (G1015) ---
MATCH (ta:ThreatActor {name: 'Scattered Spider'}), (t:Technique {id: 'T1566'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Scattered Spider'}), (t:Technique {id: 'T1078'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Scattered Spider'}), (t:Technique {id: 'T1621'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Scattered Spider'}), (t:Technique {id: 'T1556.006'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Scattered Spider'}), (t:Technique {id: 'T1528'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Salt Typhoon (G1045) ---
MATCH (ta:ThreatActor {name: 'Salt Typhoon'}), (t:Technique {id: 'T1190'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Salt Typhoon'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Salt Typhoon'}), (t:Technique {id: 'T1003.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Salt Typhoon'}), (t:Technique {id: 'T1078'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Salt Typhoon'}), (t:Technique {id: 'T1105'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Turla (G0010) ---
MATCH (ta:ThreatActor {name: 'Turla'}), (t:Technique {id: 'T1071.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Turla'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Turla'}), (t:Technique {id: 'T1027'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Turla'}), (t:Technique {id: 'T1041'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Turla'}), (t:Technique {id: 'T1568.002'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- MuddyWater (G0069) ---
MATCH (ta:ThreatActor {name: 'MuddyWater'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'MuddyWater'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'MuddyWater'}), (t:Technique {id: 'T1204.002'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'MuddyWater'}), (t:Technique {id: 'T1071.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'MuddyWater'}), (t:Technique {id: 'T1105'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- APT36 (G0134) ---
MATCH (ta:ThreatActor {name: 'APT36'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT36'}), (t:Technique {id: 'T1204.002'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT36'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT36'}), (t:Technique {id: 'T1113'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT36'}), (t:Technique {id: 'T1056.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- APT37 (G0067) ---
MATCH (ta:ThreatActor {name: 'APT37'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT37'}), (t:Technique {id: 'T1203'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT37'}), (t:Technique {id: 'T1059.005'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT37'}), (t:Technique {id: 'T1027'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT37'}), (t:Technique {id: 'T1071.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Mustang Panda (G0129) ---
MATCH (ta:ThreatActor {name: 'Mustang Panda'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Mustang Panda'}), (t:Technique {id: 'T1204.002'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Mustang Panda'}), (t:Technique {id: 'T1547.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Mustang Panda'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Mustang Panda'}), (t:Technique {id: 'T1105'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Dark Caracal (G0070) ---
MATCH (ta:ThreatActor {name: 'Dark Caracal'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Dark Caracal'}), (t:Technique {id: 'T1204.002'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Dark Caracal'}), (t:Technique {id: 'T1113'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Dark Caracal'}), (t:Technique {id: 'T1056.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Dark Caracal'}), (t:Technique {id: 'T1005'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Patchwork (G0040) ---
MATCH (ta:ThreatActor {name: 'Patchwork'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Patchwork'}), (t:Technique {id: 'T1203'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Patchwork'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Patchwork'}), (t:Technique {id: 'T1105'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Patchwork'}), (t:Technique {id: 'T1027'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Pink Sandstorm / Agrius (G1030) ---
MATCH (ta:ThreatActor {name: 'Pink Sandstorm'}), (t:Technique {id: 'T1486'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Pink Sandstorm'}), (t:Technique {id: 'T1561.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Pink Sandstorm'}), (t:Technique {id: 'T1078'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Pink Sandstorm'}), (t:Technique {id: 'T1190'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Pink Sandstorm'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- APT10 (G0045) ---
MATCH (ta:ThreatActor {name: 'APT10'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT10'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT10'}), (t:Technique {id: 'T1071.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT10'}), (t:Technique {id: 'T1003.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'APT10'}), (t:Technique {id: 'T1005'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- Kimsuky (G0094) ---
MATCH (ta:ThreatActor {name: 'Kimsuky'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Kimsuky'}), (t:Technique {id: 'T1059.005'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Kimsuky'}), (t:Technique {id: 'T1056.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Kimsuky'}), (t:Technique {id: 'T1204.002'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'Kimsuky'}), (t:Technique {id: 'T1071.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);

// --- SideWinder (G0121) ---
MATCH (ta:ThreatActor {name: 'SideWinder'}), (t:Technique {id: 'T1566.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'SideWinder'}), (t:Technique {id: 'T1203'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'SideWinder'}), (t:Technique {id: 'T1059.001'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'SideWinder'}), (t:Technique {id: 'T1027'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);
MATCH (ta:ThreatActor {name: 'SideWinder'}), (t:Technique {id: 'T1105'})
MERGE (ta)-[:USES_TECHNIQUE {confidence: 'high', source: 'MITRE ATT&CK'}]->(t);


// ============================================================
// === MalwareFamily nodes ====================================
// ============================================================

MERGE (m:MalwareFamily {name: 'CHOPSTICK'})
SET m.mitre_id = 'S0023',
    m.type = 'modular_implant',
    m.aliases = ['X-Agent', 'Sofacy'],
    m.platforms = ['Windows', 'Linux', 'iOS', 'Android'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'PlugX'})
SET m.mitre_id = 'S0013',
    m.type = 'modular_implant',
    m.aliases = ['Destroy RAT', 'Sogu', 'Kaba', 'Korplug'],
    m.platforms = ['Windows'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'Snake'})
SET m.mitre_id = 'S0022',
    m.type = 'rootkit',
    m.aliases = ['Uroburos', 'Turla Snake'],
    m.platforms = ['Windows', 'Linux', 'macOS'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'Kazuar'})
SET m.mitre_id = 'S0265',
    m.type = 'backdoor',
    m.aliases = [],
    m.platforms = ['Windows'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'CrimsonRAT'})
SET m.mitre_id = 'S0115',
    m.type = 'rat',
    m.aliases = ['Crimson', 'SEEDOOR'],
    m.platforms = ['Windows'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'RoKRAT'})
SET m.mitre_id = 'S0240',
    m.type = 'rat',
    m.aliases = ['DOGCALL'],
    m.platforms = ['Windows'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'Bandook'})
SET m.mitre_id = 'S0234',
    m.type = 'rat',
    m.aliases = [],
    m.platforms = ['Windows'],
    m.custom = false;

MERGE (m:MalwareFamily {name: 'SnapyBee'})
SET m.type = 'backdoor',
    m.aliases = ['Deed RAT'],
    m.platforms = ['Windows'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'DEMODEX'})
SET m.type = 'rootkit',
    m.aliases = [],
    m.platforms = ['Windows'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'Apostle'})
SET m.mitre_id = 'S1133',
    m.type = 'wiper_ransomware',
    m.aliases = [],
    m.platforms = ['Windows'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'BabyShark'})
SET m.mitre_id = 'S0414',
    m.type = 'reconnaissance_tool',
    m.aliases = ['LATEOP'],
    m.platforms = ['Windows'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'BADNEWS'})
SET m.mitre_id = 'S0128',
    m.type = 'backdoor',
    m.aliases = [],
    m.platforms = ['Windows'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'LoJax'})
SET m.mitre_id = 'S0397',
    m.type = 'uefi_rootkit',
    m.aliases = [],
    m.platforms = ['Windows'],
    m.custom = true;

MERGE (m:MalwareFamily {name: 'GooseEgg'})
SET m.type = 'privilege_escalation_tool',
    m.aliases = [],
    m.platforms = ['Windows'],
    m.cve = 'CVE-2022-38028',
    m.custom = true;

MERGE (m:MalwareFamily {name: 'Cobalt Strike'})
SET m.mitre_id = 'S0154',
    m.type = 'c2_framework',
    m.aliases = ['CobaltStrike', 'Beacon'],
    m.platforms = ['Windows', 'Linux', 'macOS'],
    m.custom = false;

MERGE (m:MalwareFamily {name: 'Mimikatz'})
SET m.mitre_id = 'S0002',
    m.type = 'credential_dumper',
    m.aliases = [],
    m.platforms = ['Windows'],
    m.custom = false;


// ============================================================
// === ThreatActor -[:DEPLOYS]-> MalwareFamily edges ==========
// ============================================================

// APT28 deploys CHOPSTICK, LoJax, GooseEgg, Mimikatz, Cobalt Strike
MATCH (ta:ThreatActor {name: 'APT28'}), (m:MalwareFamily {name: 'CHOPSTICK'})
MERGE (ta)-[:DEPLOYS]->(m);
MATCH (ta:ThreatActor {name: 'APT28'}), (m:MalwareFamily {name: 'LoJax'})
MERGE (ta)-[:DEPLOYS]->(m);
MATCH (ta:ThreatActor {name: 'APT28'}), (m:MalwareFamily {name: 'GooseEgg'})
MERGE (ta)-[:DEPLOYS]->(m);
MATCH (ta:ThreatActor {name: 'APT28'}), (m:MalwareFamily {name: 'Mimikatz'})
MERGE (ta)-[:DEPLOYS]->(m);

// APT29 deploys Cobalt Strike, Mimikatz
MATCH (ta:ThreatActor {name: 'APT29'}), (m:MalwareFamily {name: 'Cobalt Strike'})
MERGE (ta)-[:DEPLOYS]->(m);
MATCH (ta:ThreatActor {name: 'APT29'}), (m:MalwareFamily {name: 'Mimikatz'})
MERGE (ta)-[:DEPLOYS]->(m);

// APT33 deploys Mimikatz
MATCH (ta:ThreatActor {name: 'APT33'}), (m:MalwareFamily {name: 'Mimikatz'})
MERGE (ta)-[:DEPLOYS]->(m);

// APT34 deploys Mimikatz
MATCH (ta:ThreatActor {name: 'APT34'}), (m:MalwareFamily {name: 'Mimikatz'})
MERGE (ta)-[:DEPLOYS]->(m);

// APT41 deploys PlugX, Cobalt Strike
MATCH (ta:ThreatActor {name: 'APT41'}), (m:MalwareFamily {name: 'PlugX'})
MERGE (ta)-[:DEPLOYS]->(m);
MATCH (ta:ThreatActor {name: 'APT41'}), (m:MalwareFamily {name: 'Cobalt Strike'})
MERGE (ta)-[:DEPLOYS]->(m);

// Lazarus deploys Cobalt Strike, Mimikatz
MATCH (ta:ThreatActor {name: 'Lazarus'}), (m:MalwareFamily {name: 'Cobalt Strike'})
MERGE (ta)-[:DEPLOYS]->(m);
MATCH (ta:ThreatActor {name: 'Lazarus'}), (m:MalwareFamily {name: 'Mimikatz'})
MERGE (ta)-[:DEPLOYS]->(m);

// FIN7 deploys Cobalt Strike, Mimikatz
MATCH (ta:ThreatActor {name: 'FIN7'}), (m:MalwareFamily {name: 'Cobalt Strike'})
MERGE (ta)-[:DEPLOYS]->(m);
MATCH (ta:ThreatActor {name: 'FIN7'}), (m:MalwareFamily {name: 'Mimikatz'})
MERGE (ta)-[:DEPLOYS]->(m);

// Turla deploys Snake, Kazuar
MATCH (ta:ThreatActor {name: 'Turla'}), (m:MalwareFamily {name: 'Snake'})
MERGE (ta)-[:DEPLOYS]->(m);
MATCH (ta:ThreatActor {name: 'Turla'}), (m:MalwareFamily {name: 'Kazuar'})
MERGE (ta)-[:DEPLOYS]->(m);

// Salt Typhoon deploys SnapyBee, DEMODEX, PlugX
MATCH (ta:ThreatActor {name: 'Salt Typhoon'}), (m:MalwareFamily {name: 'SnapyBee'})
MERGE (ta)-[:DEPLOYS]->(m);
MATCH (ta:ThreatActor {name: 'Salt Typhoon'}), (m:MalwareFamily {name: 'DEMODEX'})
MERGE (ta)-[:DEPLOYS]->(m);
MATCH (ta:ThreatActor {name: 'Salt Typhoon'}), (m:MalwareFamily {name: 'PlugX'})
MERGE (ta)-[:DEPLOYS]->(m);

// APT36 deploys CrimsonRAT
MATCH (ta:ThreatActor {name: 'APT36'}), (m:MalwareFamily {name: 'CrimsonRAT'})
MERGE (ta)-[:DEPLOYS]->(m);

// APT37 deploys RoKRAT
MATCH (ta:ThreatActor {name: 'APT37'}), (m:MalwareFamily {name: 'RoKRAT'})
MERGE (ta)-[:DEPLOYS]->(m);

// Mustang Panda deploys PlugX
MATCH (ta:ThreatActor {name: 'Mustang Panda'}), (m:MalwareFamily {name: 'PlugX'})
MERGE (ta)-[:DEPLOYS]->(m);

// Dark Caracal deploys Bandook
MATCH (ta:ThreatActor {name: 'Dark Caracal'}), (m:MalwareFamily {name: 'Bandook'})
MERGE (ta)-[:DEPLOYS]->(m);

// Patchwork deploys BADNEWS
MATCH (ta:ThreatActor {name: 'Patchwork'}), (m:MalwareFamily {name: 'BADNEWS'})
MERGE (ta)-[:DEPLOYS]->(m);

// Pink Sandstorm deploys Apostle
MATCH (ta:ThreatActor {name: 'Pink Sandstorm'}), (m:MalwareFamily {name: 'Apostle'})
MERGE (ta)-[:DEPLOYS]->(m);

// APT10 deploys PlugX
MATCH (ta:ThreatActor {name: 'APT10'}), (m:MalwareFamily {name: 'PlugX'})
MERGE (ta)-[:DEPLOYS]->(m);

// Kimsuky deploys BabyShark
MATCH (ta:ThreatActor {name: 'Kimsuky'}), (m:MalwareFamily {name: 'BabyShark'})
MERGE (ta)-[:DEPLOYS]->(m);

// Scattered Spider deploys Mimikatz (credential focus)
MATCH (ta:ThreatActor {name: 'Scattered Spider'}), (m:MalwareFamily {name: 'Mimikatz'})
MERGE (ta)-[:DEPLOYS]->(m);

// MuddyWater deploys Cobalt Strike
MATCH (ta:ThreatActor {name: 'MuddyWater'}), (m:MalwareFamily {name: 'Cobalt Strike'})
MERGE (ta)-[:DEPLOYS]->(m);

// SideWinder deploys Cobalt Strike
MATCH (ta:ThreatActor {name: 'SideWinder'}), (m:MalwareFamily {name: 'Cobalt Strike'})
MERGE (ta)-[:DEPLOYS]->(m);


// ============================================================
// === New MoC navigation categories ==========================
// ============================================================

MERGE (n:MoC {name: 'edge-device-attacks'})
SET n.description = 'Router, firewall, VPN appliance exploitation',
    n.parent_phase = 'ics-ot';

MERGE (n:MoC {name: 'mobile-attacks'})
SET n.description = 'Android/iOS application attacks',
    n.parent_phase = 'mobile';

MERGE (n:MoC {name: 'ransomware-operations'})
SET n.description = 'Ransomware deployment and affiliate chains',
    n.parent_phase = 'persistence';

MERGE (n:MoC {name: 'supply-chain-attacks'})
SET n.description = 'Software/hardware supply chain compromise',
    n.parent_phase = 'supply-chain';

MERGE (n:MoC {name: 'iot-ot-attacks'})
SET n.description = 'ICS/IoT/OT targeting',
    n.parent_phase = 'ics-ot';


// ============================================================
// === COUNTERED_BY edges (Offensive Vaccine loop) ============
// ============================================================

// Password Spraying countered by credential-access knowledge
MATCH (t:Technique {id: 'T1110.003'}), (s:Skill {name: 'credential-access'})
MERGE (t)-[:COUNTERED_BY {method: 'phishing-resistant MFA, account lockout policies, conditional access'}]->(s);

// Spearphishing Attachment countered by adversary-emulation knowledge
MATCH (t:Technique {id: 'T1566.001'}), (s:Skill {name: 'adversary-emulation'})
MERGE (t)-[:COUNTERED_BY {method: 'email gateway filtering, attachment sandboxing, user awareness training'}]->(s);

// PowerShell execution countered by command-injection knowledge
MATCH (t:Technique {id: 'T1059.001'}), (s:Skill {name: 'command-injection'})
MERGE (t)-[:COUNTERED_BY {method: 'constrained language mode, script block logging, AMSI, application allowlisting'}]->(s);

// LSASS credential dumping countered by AD knowledge
MATCH (t:Technique {id: 'T1003.001'}), (s:Skill {name: 'ad'})
MERGE (t)-[:COUNTERED_BY {method: 'credential guard, LSASS PPL, restricted admin mode, LSASS audit logging'}]->(s);

// Exploit Public-Facing Application countered by web exploitation knowledge
MATCH (t:Technique {id: 'T1190'}), (s:Skill {name: 'web'})
MERGE (t)-[:COUNTERED_BY {method: 'patch management, WAF, vulnerability scanning, input validation'}]->(s);

// Valid Accounts countered by credential-access knowledge
MATCH (t:Technique {id: 'T1078'}), (s:Skill {name: 'credential-access'})
MERGE (t)-[:COUNTERED_BY {method: 'MFA enforcement, privileged access workstations, JIT access, anomaly detection'}]->(s);

// Data Encrypted for Impact countered by adversary-emulation knowledge
MATCH (t:Technique {id: 'T1486'}), (s:Skill {name: 'adversary-emulation'})
MERGE (t)-[:COUNTERED_BY {method: 'offline immutable backups, volume shadow copy protection, EDR with ransomware rollback'}]->(s);

// Software Supply Chain Compromise countered by CI/CD knowledge
MATCH (t:Technique {id: 'T1195.002'}), (s:Skill {name: 'cicd'})
MERGE (t)-[:COUNTERED_BY {method: 'SCA tools, SBOM verification, code signing validation, pinned dependencies'}]->(s);

// Scheduled Task persistence countered by lateral-movement knowledge
MATCH (t:Technique {id: 'T1053.005'}), (s:Skill {name: 'lateral-movement'})
MERGE (t)-[:COUNTERED_BY {method: 'scheduled task auditing, GPO restrictions, sysmon EventID 1 monitoring'}]->(s);

// C2 Web Protocols countered by C2 knowledge
MATCH (t:Technique {id: 'T1071.001'}), (s:Skill {name: 'c2'})
MERGE (t)-[:COUNTERED_BY {method: 'TLS inspection, DNS monitoring, network segmentation, egress allowlisting'}]->(s);

// Obfuscated Files countered by anti-debug-bypass (RE) knowledge
MATCH (t:Technique {id: 'T1027'}), (s:Skill {name: 'anti-debug-bypass'})
MERGE (t)-[:COUNTERED_BY {method: 'behavioral detection, AMSI, automated deobfuscation, sandbox analysis'}]->(s);
