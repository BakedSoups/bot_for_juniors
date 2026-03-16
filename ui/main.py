from nicegui import ui, app
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
app.mount('/static', StaticFiles(directory='static'), name='static')

@app.get('/jhon')
def index(): 
    return FileResponse('static/index.html')

@ui.page('/') 
def main(): 
    ui.run_javascript('window.location.href = "/jhon"')


ui.run(native=True, reload=False, port=8000)