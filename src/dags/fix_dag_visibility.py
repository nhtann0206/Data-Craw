from airflow.models import DagBag, DagModel
from airflow.utils.session import create_session
import logging

def fix_missing_dags():
    """Fix DAGs that are running but not visible in the UI"""
    logging.info("Running fix for missing DAGs")
    
    # Load all DAGs from filesystem
    dagbag = DagBag()
    
    with create_session() as session:
        # Get all DAG IDs from files
        file_dag_ids = set(dagbag.dags.keys())
        logging.info(f"DAGs from files: {file_dag_ids}")
        
        # Get all DAG IDs from database
        db_dag_ids = {dag.dag_id for dag in session.query(DagModel).all()}
        logging.info(f"DAGs from DB: {db_dag_ids}")
        
        # Find missing DAGs
        missing_dags = file_dag_ids - db_dag_ids
        
        if missing_dags:
            logging.info(f"Found missing DAGs: {missing_dags}")
            for dag_id in missing_dags:
                dag = dagbag.get_dag(dag_id)
                dag.sync_to_db()
                logging.info(f"Synced {dag_id} to database")
        else:
            logging.info("No missing DAGs found")
        
        # Check for paused DAGs that should be unpaused
        for dag_id in file_dag_ids:
            dag_model = session.query(DagModel).filter(DagModel.dag_id == dag_id).first()
            if dag_model and dag_model.is_paused:
                logging.info(f"Unpausing DAG: {dag_id}")
                dag_model.is_paused = False
                session.merge(dag_model)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    fix_missing_dags()
