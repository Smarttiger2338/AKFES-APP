from __future__ import annotations

import base64
import binascii
import os
import struct
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"AKFES2\x00"
VERSION = 1
SALT_SIZE = 16
NONCE_SIZE = 12
KEY_SIZE = 32
FIXED_HEADER_SIZE = len(MAGIC) + 1 + 4 + SALT_SIZE + NONCE_SIZE + 2


class FileCryptoError(Exception):
    pass


class InvalidFileFormatError(FileCryptoError):
    pass


class FileAuthenticationError(FileCryptoError):
    pass


@dataclass(frozen=True, slots=True)
class FileResult:
    filename: str
    data: bytes


class FileCryptoService:
    def __init__(self, *, iterations: int, max_file_bytes: int) -> None:
        if iterations < 100_000:
            raise ValueError("PBKDF2 iterations must be at least 100000")
        if max_file_bytes < 1:
            raise ValueError("max_file_bytes must be positive")
        self.iterations = iterations
        self.max_file_bytes = max_file_bytes

    @staticmethod
    def normalize_password(password: str) -> bytes:
        normalized = password.encode("utf-8")
        if not normalized:
            raise ValueError("password is required")
        if len(normalized) > 256:
            raise ValueError("password must not exceed 256 UTF-8 bytes")
        return normalized

    @staticmethod
    def normalize_filename(filename: str) -> str:
        normalized = filename.strip().replace("\\", "/").split("/")[-1]
        if not normalized or normalized in {".", ".."}:
            raise ValueError("filename is required")
        encoded = normalized.encode("utf-8")
        if len(encoded) > 1024:
            raise ValueError("filename is too long")
        return normalized

    def decode_base64(self, value: str, *, encrypted: bool = False) -> bytes:
        try:
            data = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as error:
            raise InvalidFileFormatError("data_base64 is not valid Base64") from error
        maximum = self.max_file_bytes + (4096 if encrypted else 0)
        if len(data) > maximum:
            raise ValueError("file exceeds the configured size limit")
        return data

    @staticmethod
    def encode_base64(data: bytes) -> str:
        return base64.b64encode(data).decode("ascii")

    @staticmethod
    def derive_key(password: bytes, salt: bytes, iterations: int) -> bytes:
        return PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_SIZE,
            salt=salt,
            iterations=iterations,
        ).derive(password)

    def encrypt(self, *, filename: str, password: str, plaintext: bytes) -> FileResult:
        if len(plaintext) > self.max_file_bytes:
            raise ValueError("file exceeds the configured size limit")
        original_filename = self.normalize_filename(filename)
        filename_bytes = original_filename.encode("utf-8")
        password_bytes = self.normalize_password(password)
        salt = os.urandom(SALT_SIZE)
        nonce = os.urandom(NONCE_SIZE)
        header = b"".join(
            (
                MAGIC,
                bytes((VERSION,)),
                struct.pack(">I", self.iterations),
                salt,
                nonce,
                struct.pack(">H", len(filename_bytes)),
                filename_bytes,
            )
        )
        key = self.derive_key(password_bytes, salt, self.iterations)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext, header)
        return FileResult(filename=f"{original_filename}.akfes", data=header + ciphertext)

    def decrypt(self, *, password: str, encrypted_data: bytes) -> FileResult:
        if len(encrypted_data) < FIXED_HEADER_SIZE + 16:
            raise InvalidFileFormatError("encrypted file is too short")
        if not encrypted_data.startswith(MAGIC):
            raise InvalidFileFormatError("unsupported encrypted file format")
        cursor = len(MAGIC)
        version = encrypted_data[cursor]
        cursor += 1
        if version != VERSION:
            raise InvalidFileFormatError("unsupported encrypted file version")
        iterations = struct.unpack(">I", encrypted_data[cursor : cursor + 4])[0]
        cursor += 4
        if not 100_000 <= iterations <= 2_000_000:
            raise InvalidFileFormatError("invalid PBKDF2 iteration count")
        salt = encrypted_data[cursor : cursor + SALT_SIZE]
        cursor += SALT_SIZE
        nonce = encrypted_data[cursor : cursor + NONCE_SIZE]
        cursor += NONCE_SIZE
        filename_length = struct.unpack(">H", encrypted_data[cursor : cursor + 2])[0]
        cursor += 2
        if filename_length < 1 or cursor + filename_length + 16 > len(encrypted_data):
            raise InvalidFileFormatError("invalid encrypted filename metadata")
        filename_bytes = encrypted_data[cursor : cursor + filename_length]
        cursor += filename_length
        try:
            filename = self.normalize_filename(filename_bytes.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise InvalidFileFormatError("invalid encrypted filename") from error
        header = encrypted_data[:cursor]
        ciphertext = encrypted_data[cursor:]
        password_bytes = self.normalize_password(password)
        key = self.derive_key(password_bytes, salt, iterations)
        try:
            plaintext = AESGCM(key).decrypt(nonce, ciphertext, header)
        except InvalidTag as error:
            raise FileAuthenticationError("wrong password or encrypted file was modified") from error
        if len(plaintext) > self.max_file_bytes:
            raise ValueError("decrypted file exceeds the configured size limit")
        return FileResult(filename=filename, data=plaintext)
