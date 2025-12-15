import asyncio
import os
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Optional
import tempfile
import json
from datetime import datetime
from pathlib import Path
from main import process_workflow

app = FastAPI(title="Company Web Scraper API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

log_streams = {}


class LogCollector:
    def __init__(self, job_id):
        self.job_id = job_id
        self.logs = []

    def add_log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        log_streams[self.job_id].append(log_entry)


def process_file_task_sync(file_path: str, city: str, country: str, job_id: str):
    log_collector = LogCollector(job_id)

    def log_callback(msg):
        log_collector.add_log(msg)

    try:
        log_callback(f"Starting processing for location: {city} {country}")
        output_file = process_workflow(
            input_file=file_path,
            city=city,
            country=country,
            log_callback=log_callback
        )
        log_callback(f"Processing completed! Output file: {output_file}")

        if job_id in log_streams:
            log_streams[job_id].append(f"__COMPLETED__{output_file}")

    except Exception as e:
        log_callback(f"Error during processing: {str(e)}")
        if job_id in log_streams:
            log_streams[job_id].append(f"__ERROR__{str(e)}")
    finally:
        try:
            os.remove(file_path)
        except:
            pass

async def process_file_task(file_path: str, city: str, country: str, job_id: str):
    import threading
    thread = threading.Thread(
        target=process_file_task_sync,
        args=(file_path, city, country, job_id)
    )
    thread.start()


@app.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    city: str = Form(...),
    country: str = Form(...)
):
    if not city or not city.strip():
        return {"error": "City is required and cannot be empty"}

    if not country or not country.strip():
        return {"error": "Country is required and cannot be empty"}

    if not (file.filename.endswith('.xlsx') or file.filename.endswith('.csv')):
        return {"error": "Only .xlsx and .csv files are supported"}

    job_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}"

    log_streams[job_id] = []

    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix='.xlsx' if file.filename.endswith('.xlsx') else '.csv'
    )

    try:
        contents = await file.read()
        temp_file.write(contents)
        temp_file.close()

        asyncio.create_task(process_file_task(temp_file.name, city, country, job_id))

        return {
            "message": "File uploaded successfully. Processing started.",
            "job_id": job_id,
            "city": city,
            "country": country,
            "filename": file.filename
        }

    except Exception as e:
        os.remove(temp_file.name)
        return {"error": f"Failed to process file: {str(e)}"}


@app.get("/logs/{job_id}")
async def stream_logs(job_id: str):
    async def event_generator():
        sent_count = 0

        while True:
            if job_id not in log_streams:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            logs = log_streams[job_id]

            while sent_count < len(logs):
                log_entry = logs[sent_count]

                if log_entry.startswith("__COMPLETED__"):
                    output_file = log_entry.replace("__COMPLETED__", "")
                    yield f"data: {json.dumps({'type': 'completed', 'output_file': output_file})}\n\n"
                    await asyncio.sleep(2)
                    del log_streams[job_id]
                    return

                elif log_entry.startswith("__ERROR__"):
                    error_msg = log_entry.replace("__ERROR__", "")
                    yield f"data: {json.dumps({'type': 'error', 'message': error_msg})}\n\n"
                    await asyncio.sleep(2)
                    del log_streams[job_id]
                    return

                else:
                    yield f"data: {json.dumps({'type': 'log', 'message': log_entry})}\n\n"

                sent_count += 1

            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = filename

    if not os.path.exists(file_path):
        return {"error": "File not found"}

    return FileResponse(
        file_path,
        media_type="text/csv",
        filename=os.path.basename(file_path)
    )


@app.get("/", response_class=HTMLResponse)
async def root():
    html_file = Path(__file__).parent / "index.html"
    if html_file.exists():
        return html_file.read_text()
    return """
    <html>
        <body>
            <h1Web Scraper API</h1>
            <p>Frontend UI not found. Please ensure index.html is available.</p>
        </body>
    </html>
    """


@app.get("/api/health")
async def health():
    return {
        "message": "Web Scraper API",
        "version": "1.0.0",
        "status": "running"
    }


# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8000)
