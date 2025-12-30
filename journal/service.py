from db.supabase_client import supabase

TABLE_NAME = "trade_journal"


def fetch_all_journals():
    res = supabase.table(TABLE_NAME).select("*").execute()
    return res.data


def create_journal_entry(entry: dict):
    res = supabase.table(TABLE_NAME).insert(entry).execute()
    return res.data[0]
