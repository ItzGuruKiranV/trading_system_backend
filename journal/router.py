from fastapi import APIRouter
from typing import List

from journal.models import JournalCreate, JournalOut
from journal.service import fetch_all_journals, create_journal_entry

router = APIRouter(prefix="/api/journal")


@router.get("", response_model=List[JournalOut])
def get_journals():
    # ❌ NO try/except
    return fetch_all_journals()


@router.post("", response_model=JournalOut)
def create_journal(entry: JournalCreate):
    # ❌ NO try/except
    return create_journal_entry(entry.dict())
