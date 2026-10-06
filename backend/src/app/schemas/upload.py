from pydantic import BaseModel


class UploadedImage(BaseModel):
    # What to put in image_urls or avatar_path: served by nginx under /media/
    path: str
