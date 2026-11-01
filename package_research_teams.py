"""Add-only research/team toolkit: never bundle source exports or model weights."""
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
FILES=('slater_discord_research.py','slater_team_env.py','slater_team_eval.py','slater_team_campaign.py',
    'slater_attention_native_probe.py','SLATER_21_CHECK_CURRENT_MODEL.bat','SLATER_22_ATTENTION_NATIVE_PROBE.bat',
    'SLATER_23_TEAM_EXPERIMENT.bat','SLATER_23_PAUSE.bat','SLATER_23_STATUS.bat',
    'SLATER_RESEARCH_AND_TEAMS_README.md','docs/DISCORD_RESEARCH_FINDINGS.md','docs/FRAMEWORK_RESEARCH.md',
    'docs/ATTENTION_NATIVE_COMPATIBILITY.md','docs/TEAM_FORMATS.md','docs/UPDATE180_CONTINUE02_RESULTS.md',
    'GigaLearn_Project/Native_Backend/attention_probe/CMakeLists.txt',
    'GigaLearn_Project/Native_Backend/attention_probe/AttentionProbe.cpp')


def build():
    out=ROOT/'Slater_Research_and_Team_Update.zip'
    for name in FILES:
        p=Path(name)
        if p.is_absolute() or '..' in p.parts or p.parts[0] in ('data','attachments'):
            raise ValueError('Private or unsafe artifact path')
        if p.suffix.lower() in ('.pt','.lt','.bin','.html','.rar','.sqlite3'):
            raise ValueError('Models and private exports must be excluded')
        if not (ROOT/p).is_file():raise FileNotFoundError(name)
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        for name in FILES:z.write(ROOT/name,name)
    with ZipFile(out) as z:
        if z.testzip():raise ValueError('ZIP verification failed')
        assert set(z.namelist())==set(FILES)
    print(out.name,len(FILES),out.stat().st_size)

if __name__=='__main__':build()
