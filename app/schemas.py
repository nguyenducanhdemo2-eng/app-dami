from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoginRequest(BaseModel):
    password: str = Field(min_length=1, max_length=512)


class SearchRequest(BaseModel):
    q: str = Field(min_length=2, max_length=100)
    search_type: Literal["TOP", "RECENT"] = "RECENT"
    search_mode: Literal["KEYWORD", "TAG"] = "KEYWORD"
    limit: int = Field(default=10, ge=1, le=25)

    @field_validator("q")
    @classmethod
    def clean_query(cls, value: str) -> str:
        return " ".join(value.split())


class QueueCandidate(BaseModel):
    id: str = Field(min_length=1, max_length=200)
    username: str = Field(default="", max_length=100)
    text: str = Field(default="", max_length=5000)
    permalink: str = Field(default="", max_length=2000)


class QueueAddRequest(BaseModel):
    items: list[QueueCandidate] = Field(min_length=1, max_length=10)
    template: str = Field(min_length=1, max_length=500)
    keyword: str = Field(default="", max_length=100)


class QueueEditRequest(BaseModel):
    reply_text: str = Field(min_length=1, max_length=500)


class SendRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=10)


class TokenConnectRequest(BaseModel):
    access_token: str = Field(min_length=20, max_length=4096)
    expires_in: int = Field(default=5_184_000, ge=60, le=6_000_000)

