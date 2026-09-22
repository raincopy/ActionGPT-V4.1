import uvicorn
from liq_analysis_server.config import SERVER_HOST,SERVER_PORT
if __name__=="__main__":uvicorn.run("liq_analysis_server.api:app",host=SERVER_HOST,port=SERVER_PORT,reload=False)

