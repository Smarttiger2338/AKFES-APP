import pytest

from app.file_crypto import (
    FileAuthenticationError,
    FileCryptoService,
    InvalidFileFormatError,
)


def make_service() -> FileCryptoService:
    return FileCryptoService(iterations=100_000, max_file_bytes=1024 * 1024)


def test_encrypt_decrypt_round_trip() -> None:
    service = make_service()
    plaintext = b"AKFES file encryption test\x00\x01\xff"

    encrypted = service.encrypt(
        filename="report.txt",
        password="correct horse battery staple",
        plaintext=plaintext,
    )

    assert encrypted.filename == "report.txt.akfes"
    assert encrypted.data != plaintext
    assert encrypted.data.startswith(b"AKFES2\x00")

    decrypted = service.decrypt(
        password="correct horse battery staple",
        encrypted_data=encrypted.data,
    )

    assert decrypted.filename == "report.txt"
    assert decrypted.data == plaintext


def test_wrong_password_and_tampering_are_rejected() -> None:
    service = make_service()
    encrypted = service.encrypt(
        filename="photo.png",
        password="right-password",
        plaintext=b"image bytes",
    )

    with pytest.raises(FileAuthenticationError):
        service.decrypt(password="wrong-password", encrypted_data=encrypted.data)

    tampered = bytearray(encrypted.data)
    tampered[-1] ^= 1
    with pytest.raises(FileAuthenticationError):
        service.decrypt(password="right-password", encrypted_data=bytes(tampered))


def test_invalid_format_and_size_limit_are_rejected() -> None:
    service = FileCryptoService(iterations=100_000, max_file_bytes=8)

    with pytest.raises(ValueError):
        service.encrypt(filename="large.bin", password="password", plaintext=b"123456789")

    with pytest.raises(InvalidFileFormatError):
        service.decrypt(password="password", encrypted_data=b"not-an-akfes-file")


def test_filename_is_sanitized_before_encryption() -> None:
    service = make_service()
    encrypted = service.encrypt(
        filename="../unsafe/path/document.pdf",
        password="password",
        plaintext=b"pdf",
    )
    decrypted = service.decrypt(password="password", encrypted_data=encrypted.data)

    assert encrypted.filename == "document.pdf.akfes"
    assert decrypted.filename == "document.pdf"
