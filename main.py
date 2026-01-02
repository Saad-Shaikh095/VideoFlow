import os
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import yt_dlp
import traceback
import urllib.parse

app = FastAPI()

# Mount static files
if not os.path.exists("static"):
    os.makedirs("static")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_index():
    return FileResponse("static/index.html")

@app.post("/fetch-info")
async def fetch_info(request: Request):
    data = await request.json()
    url = data.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    # More robust options
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'best',
        # Handle YouTube and Instagram cookie/auth issues if needed
        # 'cookiefile': 'cookies.txt', 
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Extract basic info
            video_info = {
                "title": info.get("title", "Unknown Title"),
                "thumbnail": info.get("thumbnail"),
                "duration": info.get("duration"),
                "uploader": info.get("uploader"),
                "formats": []
            }

            # Filter formats for better UI selection
            # We prioritize combined formats (video+audio) for direct proxy
            formats = info.get("formats", [])
            for f in formats:
                # Basic filter for workable formats
                if f.get("vcodec") != "none" and f.get("acodec") != "none" and f.get("ext") == "mp4":
                    video_info["formats"].append({
                        "format_id": f.get("format_id"),
                        "ext": f.get("ext"),
                        "resolution": f.get("resolution") or f.get("format_note") or "Auto",
                        "filesize": f.get("filesize"),
                        "url": f.get("url")
                    })
            
            # Fallback for Instagram or limited formats
            if not video_info["formats"]:
                 video_info["formats"].append({
                        "format_id": "best",
                        "ext": info.get("ext", "mp4"),
                        "resolution": "Best Quality",
                        "url": info.get("url")
                    })

            return video_info
    except Exception as e:
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/proxy-download")
async def proxy_download(url: str, filename: str):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    
    # Sanitize filename
    clean_filename = "".join(c for c in filename if c.isalnum() or c in (' ', '.', '_')).rstrip()
    if not clean_filename:
        clean_filename = "video"
    if not clean_filename.lower().endswith(".mp4"):
        clean_filename += ".mp4"

    async def stream_video():
        async with httpx.AsyncClient(follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    yield b"Error fetching video"
                    return
                async for chunk in response.aiter_bytes():
                    yield chunk

    # Proper content-disposition to force download
    headers = {
        "Content-Disposition": f'attachment; filename="{clean_filename}"'
    }
    return StreamingResponse(stream_video(), media_type="video/mp4", headers=headers)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
