from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from client.opc_classic import runtime
R=Path('app/routes.py').read_text();T=Path('app/templates/opc_classic_studio.html').read_text();X=Path('client/opc_classic/runtime.py').read_text()
def test_studio_and_edge_contract():
 assert 'OPC Classic Windows Bridge' in T
 assert '/api/v1/edge/opc-classic/' in R and "connector_type='OPC_CLASSIC'" in R
 assert 'windows_only=True' in R and 'allow_write=False' in R and 'allow_alarm_ack=False' in R
def test_runtime_is_windows_only_and_read_only():
 assert "os.name!='nt'" in X and 'opc_classic_requires_windows' in X
 for forbidden in ('def write(','def set(','def execute(','def alarm_ack('):assert forbidden not in X
def test_bounded_browse_and_read():
 assert 'min(1000' in X and "len(item_ids)>500" in X
def test_quality_normalisation():
 assert runtime._quality('Good')=='GOOD' and runtime._quality('Bad')=='BAD' and runtime._quality('Uncertain')=='UNCERTAIN'
def test_dcom_not_exposed():
 assert 'never exposes DCOM to the internet' in T and 'outbound HTTPS' in T
def test_mapping_contract():
 assert 'opcda:item:' in R and 'source_timestamp' in X and 'sequence' in X
