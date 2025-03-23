# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>
# Copyright (C) 2025 Luis Garcia <git@luigi311.com>

import os
import json
import aiosqlite
import aiofiles
import msgspec
from common.utils import store_print

async def init_database(database_path, verbose=False):
    """Initialize the SQLite database"""
    os.makedirs(os.path.dirname(database_path), exist_ok=True)

    db = await aiosqlite.connect(database_path)
    await db.execute("PRAGMA journal_mode = WAL")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS apps (
            repository TEXT NOT NULL,
            package_id TEXT NOT NULL,
            repository_url TEXT NOT NULL,
            name TEXT,
            summary TEXT,
            description TEXT,
            license TEXT,
            categories TEXT,
            author TEXT,
            web_url TEXT,
            source_url TEXT,
            tracker_url TEXT,
            changelog_url TEXT,
            donation_url TEXT,
            added_date TEXT,
            last_updated TEXT,
            package JSON,
            PRIMARY KEY (repository, package_id)
        )
    """)

    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_apps_lower_name ON apps(LOWER(name));
    """)

    await db.commit()
    store_print("Database initialized", verbose)

    return db

async def save_packages_to_db(db, packages, json_enc, verbose=False):
    """Save packages to the database"""
    try:
        async with db.execute("BEGIN TRANSACTION;"):
            await db.execute("DELETE FROM apps;")

            if packages:
                await db.executemany(
                    """
                    INSERT INTO apps (
                        repository, package_id, repository_url, name, summary, description, license,
                        categories, author, web_url, source_url, tracker_url, changelog_url,
                        donation_url, added_date, last_updated, package
                    )
                    VALUES (
                        :repository, :package_id, :repository_url, :name, :summary, :description, :license,
                        :categories, :author, :web_url, :source_url, :tracker_url, :changelog_url,
                        :donation_url, :added_date, :last_updated, :package
                    )
                    ON CONFLICT(repository, package_id) DO UPDATE SET
                        repository_url = excluded.repository_url,
                        name = excluded.name,
                        summary = excluded.summary,
                        description = excluded.description,
                        license = excluded.license,
                        categories = excluded.categories,
                        author = excluded.author,
                        web_url = excluded.web_url,
                        source_url = excluded.source_url,
                        tracker_url = excluded.tracker_url,
                        changelog_url = excluded.changelog_url,
                        donation_url = excluded.donation_url,
                        added_date = excluded.added_date,
                        last_updated = excluded.last_updated,
                        package = excluded.package;
                    """,
                    packages,
                )
            await db.commit()
        store_print(f"Saved {len(packages)} packages to database", verbose)
        return True
    except Exception as e:
        store_print(f"Error saving packages to database: {e}", verbose)
        return False

async def ensure_populated(db, update_func, verbose=False):
    """Ensure the database is populated"""
    try:
        async with db.execute("SELECT COUNT(*) FROM apps") as cursor:
            row_count = await cursor.fetchone()

        if not row_count[0]:
            store_print("Database is empty, updating cache", verbose)
            overall_success = await update_func()

            if not overall_success:
                store_print("Database population failed", verbose)
                return False

        return True
    except Exception as e:
        store_print(f"Error checking database population: {e}", verbose)
        return False

async def search_packages(db, query, json_decoder, verbose=False):
    """Search for packages in the database"""
    results = []
    try:
        sql_query = """
            SELECT repository, package_id, name, summary, description, license,
                categories, author, web_url, source_url, tracker_url,
                changelog_url, donation_url, added_date, last_updated, package
            FROM apps
            WHERE LOWER(name) LIKE LOWER(?)
        """

        async with db.execute(sql_query, (f"%{query}%",)) as cursor:
            rows = await cursor.fetchall()
            for row in rows:
                app_info = {
                    'repository': row[0],
                    'id': row[1],
                    'name': row[2],
                    'summary': row[3],
                    'description': row[4],
                    'license': row[5],
                    'categories': json_decoder(row[6]) if row[6] else None,
                    'author': row[7],
                    'web_url': row[8],
                    'source_url': row[9],
                    'tracker_url': row[10],
                    'changelog_url': row[11],
                    'donation_url': json_decoder(row[12]) if row[12] else None,
                    'added_date': row[13],
                    'last_updated': row[14],
                    'package': json_decoder(row[15]) if row[15] else None
                }
                results.append(app_info)
        store_print(f"Found {len(results)} results for query: {query}", verbose)
        return results
    except Exception as e:
        store_print(f"Error searching packages: {e}", verbose)
        return []

async def get_package_by_id(db, package_id, json_decoder, verbose=False):
    """Get package details by ID"""
    try:
        sql_query = """
            SELECT repository, package
            FROM apps
            WHERE package_id = ?
        """

        package_info = None
        async with db.execute(sql_query, (package_id,)) as cursor:
            rows = await cursor.fetchall()
            if len(rows) > 1:
                store_print(f"Multiple entries found for {package_id}", verbose)

            for row in rows:
                repository, package_json = row
                store_print(f"Found package {package_id} in {repository}", verbose)
                package_info = json_decoder(package_json)
                break
        return package_info
    except Exception as e:
        store_print(f"Error getting package by ID: {e}", verbose)
        return None
