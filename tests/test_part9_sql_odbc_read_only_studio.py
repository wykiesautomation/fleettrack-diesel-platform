from pathlib import Path
import sys,pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from client.sql_odbc.runtime import validate_query
R=Path('app/routes.py').read_text();T=Path('app/templates/sql_odbc_studio.html').read_text();X=Path('client/sql_odbc/runtime.py').read_text()
def test_studio():assert 'SQL / ODBC READ-ONLY STUDIO' in T and '/api/v1/edge/sql-odbc/' in R and "connector_type='SQL_ODBC'" in R
def test_select():assert validate_query('SELECT value FROM process')=='SELECT value FROM process'
def test_with():assert validate_query('WITH x AS (SELECT 1 v) SELECT v FROM x').startswith('WITH')
@pytest.mark.parametrize('q',['UPDATE t SET x=1','DELETE FROM t','INSERT INTO t VALUES (1)','DROP TABLE t','EXEC sp_x','SELECT * INTO x FROM y','SELECT 1; SELECT 2','COMMIT'])
def test_block(q):
 with pytest.raises(ValueError):validate_query(q)
def test_no_commit():assert '.commit(' not in X and 'conn.rollback()' in X and 'autocommit=False' in X and 'SQL_MODE_READ_ONLY' in X
def test_limits_and_secrets():assert 'fetchmany(limit+1)' in X and 'max_rows' in R and 'credential_ref' in R
