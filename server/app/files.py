from __future__ import annotations

from io import BytesIO
from typing import Annotated
from urllib.parse import quote, unquote

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .file_crypto import (
    FileAuthenticationError,
    FileCryptoService,
    InvalidFileFormatError,
)
from .signed_requests import verify_signed_request

router = APIRouter(prefix="/files", tags=["files"])


class FileOperationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=1024)
    password: str = Field(min_length=1, max_length=128)
    data_base64: str = Field(min_length=1)


class FileOperationResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    filename: str
    data_base64: str
    size_bytes: int
    algorithm: str = "AES-256-GCM"
    key_derivation: str = "PBKDF2-HMAC-SHA256"


def get_file_crypto(request: Request) -> FileCryptoService:
    return request.app.state.file_crypto


async def require_signed_file_request(
    request: Request,
    *,
    authorization: str | None,
    challenge: str | None,
    signature: str | None,
    device_id: str | None,
) -> None:
    await verify_signed_request(
        request,
        authorization=authorization,
        challenge=challenge,
        signature=signature,
        device_id=device_id,
    )


def decode_required_header(value: str | None, name: str, *, max_length: int) -> str:
    if value is None:
        raise HTTPException(status_code=422, detail=f"Missing {name} header")
    decoded = unquote(value).strip()
    if not decoded or len(decoded) > max_length:
        raise HTTPException(status_code=422, detail=f"Invalid {name} header")
    return decoded


def binary_response(filename: str, data: bytes) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(data),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "Content-Length": str(len(data)),
            "X-AKFES-Filename": quote(filename),
            "X-AKFES-Algorithm": "AES-256-GCM",
            "X-AKFES-Key-Derivation": "PBKDF2-HMAC-SHA256",
        },
    )


@router.post("/encrypt", response_model=FileOperationResponse)
async def encrypt_file(
    payload: FileOperationRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_akfes_challenge: Annotated[str | None, Header()] = None,
    x_akfes_signature: Annotated[str | None, Header()] = None,
    x_akfes_device_id: Annotated[str | None, Header()] = None,
) -> FileOperationResponse:
    await require_signed_file_request(
        request,
        authorization=authorization,
        challenge=x_akfes_challenge,
        signature=x_akfes_signature,
        device_id=x_akfes_device_id,
    )
    service = get_file_crypto(request)
    try:
        plaintext = service.decode_base64(payload.data_base64)
        result = service.encrypt(
            filename=payload.filename,
            password=payload.password,
            plaintext=plaintext,
        )
    except (ValueError, InvalidFileFormatError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return FileOperationResponse(
        filename=result.filename,
        data_base64=service.encode_base64(result.data),
        size_bytes=len(result.data),
    )


@router.post("/decrypt", response_model=FileOperationResponse)
async def decrypt_file(
    payload: FileOperationRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_akfes_challenge: Annotated[str | None, Header()] = None,
    x_akfes_signature: Annotated[str | None, Header()] = None,
    x_akfes_device_id: Annotated[str | None, Header()] = None,
) -> FileOperationResponse:
    await require_signed_file_request(
        request,
        authorization=authorization,
        challenge=x_akfes_challenge,
        signature=x_akfes_signature,
        device_id=x_akfes_device_id,
    )
    service = get_file_crypto(request)
    try:
        encrypted_data = service.decode_base64(payload.data_base64, encrypted=True)
        result = service.decrypt(password=payload.password, encrypted_data=encrypted_data)
    except FileAuthenticationError as error:
        raise HTTPException(status_code=400, detail="Wrong password or encrypted file was modified") from error
    except (ValueError, InvalidFileFormatError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return FileOperationResponse(
        filename=result.filename,
        data_base64=service.encode_base64(result.data),
        size_bytes=len(result.data),
    )


@router.post("/encrypt-binary", response_class=StreamingResponse)
async def encrypt_file_binary(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_akfes_challenge: Annotated[str | None, Header()] = None,
    x_akfes_signature: Annotated[str | None, Header()] = None,
    x_akfes_device_id: Annotated[str | None, Header()] = None,
    x_akfes_filename: Annotated[str | None, Header()] = None,
    x_akfes_password: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    await require_signed_file_request(
        request,
        authorization=authorization,
        challenge=x_akfes_challenge,
        signature=x_akfes_signature,
        device_id=x_akfes_device_id,
    )
    filename = decode_required_header(x_akfes_filename, "filename", max_length=1024)
    password = decode_required_header(x_akfes_password, "password", max_length=128)
    plaintext = await request.body()
    service = get_file_crypto(request)
    try:
        result = service.encrypt(filename=filename, password=password, plaintext=plaintext)
    except (ValueError, InvalidFileFormatError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return binary_response(result.filename, result.data)


@router.post("/decrypt-binary", response_class=StreamingResponse)
async def decrypt_file_binary(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
    x_akfes_challenge: Annotated[str | None, Header()] = None,
    x_akfes_signature: Annotated[str | None, Header()] = None,
    x_akfes_device_id: Annotated[str | None, Header()] = None,
    x_akfes_password: Annotated[str | None, Header()] = None,
) -> StreamingResponse:
    await require_signed_file_request(
        request,
        authorization=authorization,
        challenge=x_akfes_challenge,
        signature=x_akfes_signature,
        device_id=x_akfes_device_id,
    )
    password = decode_required_header(x_akfes_password, "password", max_length=128)
    encrypted_data = await request.body()
    service = get_file_crypto(request)
    try:
        result = service.decrypt(password=password, encrypted_data=encrypted_data)
    except FileAuthenticationError as error:
        raise HTTPException(status_code=400, detail="Wrong password or encrypted file was modified") from error
    except (ValueError, InvalidFileFormatError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return binary_response(result.filename, result.data)
