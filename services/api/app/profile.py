"""Private, bounded profile portraits; no original image metadata is retained."""
from io import BytesIO
from typing import Annotated
import warnings
from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from sqlalchemy import ForeignKey, LargeBinary, String
from sqlalchemy.orm import Session, mapped_column
from .db import Base, User, get_db, now, uid
from .security import current_user, rate_limit
from .quota import lock_vault

MAX_PHOTO_BYTES = 2 * 1024 * 1024
MAX_PHOTO_PIXELS = 8_000_000
router = APIRouter(prefix='/api/v1/profile', tags=['profile'])


class ProfileImage(Base):
    __tablename__ = 'profile_images'
    user_id = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    content = mapped_column(LargeBinary, nullable=False)
    media_type = mapped_column(String(30), nullable=False, default='image/jpeg')
    version = mapped_column(String(36), nullable=False, default=uid)
    updated = mapped_column(String, nullable=False, default=now)


D = Annotated[Session, Depends(get_db)]
U = Annotated[User, Depends(current_user)]


def photo_info(photo: ProfileImage | None) -> dict:
    if photo is None:
        return {'present': False, 'version': None, 'url': None}
    return {'present': True, 'version': photo.version, 'url': '/api/v1/profile/photo?v=' + photo.version}


def normalize_photo(content: bytes) -> bytes:
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as original:
                if original.format not in {'JPEG', 'PNG', 'WEBP'}:
                    raise HTTPException(422, 'Choose a JPEG, PNG or WebP image.')
                if original.width * original.height > MAX_PHOTO_PIXELS or min(original.size) < 1:
                    raise HTTPException(422, 'Choose an image with at most 8 million pixels.')
                if getattr(original, 'n_frames', 1) != 1:
                    raise HTTPException(422, 'Choose a still image rather than an animation.')
                original.load()
                oriented = ImageOps.exif_transpose(original)
                oriented.thumbnail((512, 512), Image.Resampling.LANCZOS)
                # A fresh canvas strips EXIF, GPS, ICC and textual metadata.
                alpha = oriented.convert('RGBA')
                clean = Image.new('RGB', alpha.size, (248, 246, 239))
                clean.paste(alpha, mask=alpha.getchannel('A'))
                output = BytesIO()
                clean.save(output, format='JPEG', quality=88, optimize=True)
                return output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'This image could not be read safely. Choose another JPEG, PNG or WebP.')


@router.get('/photo/info')
def get_info(user: U, db: D):
    return photo_info(db.get(ProfileImage, user.id))


@router.get('/photo')
def get_photo(user: U, db: D):
    photo = db.get(ProfileImage, user.id)
    if photo is None:
        raise HTTPException(404, 'No profile photo is saved.')
    return Response(photo.content, media_type=photo.media_type, headers={
        'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
        'Content-Disposition': 'inline; filename="profile-photo.jpg"',
    })


@router.put('/photo')
async def put_photo(file: UploadFile, user: U, db: D):
    rate_limit('profile-photo:' + user.id, 10)
    try:
        content = await file.read(MAX_PHOTO_BYTES + 1)
    finally:
        await file.close()
    if len(content) > MAX_PHOTO_BYTES:
        raise HTTPException(413, 'Profile photos must be 2 MB or smaller.')
    if not content:
        raise HTTPException(422, 'Choose a non-empty image.')
    clean = normalize_photo(content)
    lock_vault(db, user.id)
    photo = db.get(ProfileImage, user.id)
    if photo is None:
        photo = ProfileImage(user_id=user.id)
        db.add(photo)
    photo.content, photo.media_type = clean, 'image/jpeg'
    photo.version, photo.updated = uid(), now()
    db.commit()
    return photo_info(photo)


@router.delete('/photo')
def delete_photo(user: U, db: D):
    lock_vault(db, user.id)
    photo = db.get(ProfileImage, user.id)
    if photo is not None:
        db.delete(photo)
    db.commit()
    return photo_info(None)
