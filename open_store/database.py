# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>

import aiosqlite
import json
import os

from common.utils import store_print

async def init_app_database(db_path, verbose=False):
    """
    Initialize the app database.

    Args:
        db_path: Path to the database file
        verbose: Whether to print verbose logs

    Returns:
        Database connection
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode = WAL")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS apps (
            id TEXT PRIMARY KEY,
            name TEXT,
            tagline TEXT,
            description TEXT,
            author TEXT,
            license TEXT,
            icon TEXT,
            categories TEXT,
            architectures TEXT,
            publisher TEXT,
            types TEXT,
            framework TEXT,
            channels TEXT,
            latest_version TEXT,
            published_date TEXT,
            updated_date TEXT,
            data JSON
        )
    """)

    await db.execute("""
        CREATE INDEX IF NOT EXISTS idx_apps_name ON apps(name);
    """)

    await db.commit()
    store_print("App database initialized", verbose)

    return db

async def init_installed_database(db_path, verbose=False):
    """
    Initialize the installed apps database.

    Args:
        db_path: Path to the database file
        verbose: Whether to print verbose logs

    Returns:
        Database connection
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    db = await aiosqlite.connect(db_path)
    await db.execute("PRAGMA journal_mode = WAL")

    await db.execute("""
        CREATE TABLE IF NOT EXISTS installed_apps (
            id TEXT PRIMARY KEY,
            name TEXT,
            version TEXT,
            channel TEXT,
            architecture TEXT,
            install_date TEXT,
            app_dir TEXT
        )
    """)

    await db.commit()
    store_print("Installed apps database initialized", verbose)

    return db

async def save_app_list(db, apps, verbose=False):
    """
    Save a list of apps to the database.

    Args:
        db: Database connection
        apps: List of app dictionaries
        verbose: Whether to print verbose logs

    Returns:
        True if successful, False otherwise
    """
    try:
        async with db.execute("BEGIN TRANSACTION;"):
            await db.execute("DELETE FROM apps;")

            for app in apps:
                await db.execute("""
                    INSERT INTO apps (
                        id, name, tagline, description, author, license, icon,
                        categories, architectures, publisher, types, framework,
                        channels, latest_version, published_date, updated_date, data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    app.get('id', ''),
                    app.get('name', ''),
                    app.get('tagline', ''),
                    app.get('description', ''),
                    app.get('author', ''),
                    app.get('license', ''),
                    app.get('icon', ''),
                    json.dumps(app.get('architectures', [])),
                    json.dumps(app.get('architectures', [])),
                    app.get('publisher', ''),
                    json.dumps(app.get('types', [])),
                    app.get('framework', ''),
                    json.dumps(app.get('channels', [])),
                    app.get('version', ''),
                    app.get('published_date', ''),
                    app.get('updated_date', ''),
                    json.dumps(app)
                ))

            await db.commit()

        store_print(f"Saved {len(apps)} apps to database", verbose)
        return True
    except Exception as e:
        store_print(f"Error saving apps to database: {e}", verbose)
        return False

async def search_apps(db, query, verbose=False):
    """
    Search for apps in the database.

    Args:
        db: Database connection
        query: Search query
        verbose: Whether to print verbose logs

    Returns:
        List of matching apps
    """
    results = []

    try:
        search_query = f"%{query}%"
        async with db.execute(
            """
            SELECT id, name, tagline, description, data
            FROM apps
            WHERE (name LIKE ? OR tagline LIKE ?)
            """,
            (search_query, search_query)
        ) as cursor:
            async for row in cursor:
                app_id, name, tagline, description, data = row
                app_data = json.loads(data)

                app_info = {
                    'id': app_id,
                    'name': name,
                    'summary': tagline,  # Use tagline is somewhat a summary, looks to be enough
                    'description': description,
                    'license': app_data.get('license', ''),
                    'author': app_data.get('author', ''),
                    'web_url': app_data.get('web_url', ''),
                    'repository': 'OpenStore',
                    'package': {
                        'version': app_data.get('version', ''),
                        'icon_url': app_data.get('icon', '')
                    }
                }
                results.append(app_info)

        store_print(f"Found {len(results)} apps matching '{query}'", verbose)
        return results
    except Exception as e:
        store_print(f"Error searching apps: {e}", verbose)
        return []

async def save_installed_app(db, app_id, name, version, channel, architecture,
                             install_date, app_dir, verbose=False):
    """
    Save installed app information to the database.

    Args:
        db: Database connection
        app_id: App ID
        name: App name
        version: App version
        channel: App channel
        architecture: App architecture
        install_date: Installation date
        app_dir: Path to the extracted app directory
        verbose: Whether to print verbose logs

    Returns:
        True if successful, False otherwise
    """
    try:
        await db.execute("""
            INSERT OR REPLACE INTO installed_apps
            (id, name, version, channel, architecture, install_date, app_dir)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            app_id,
            name,
            version,
            channel,
            architecture,
            install_date,
            app_dir
        ))
        await db.commit()

        store_print(f"Saved installed app {app_id} to database", verbose)
        return True
    except Exception as e:
        store_print(f"Error saving installed app: {e}", verbose)
        return False

async def remove_installed_app(db, app_id, verbose=False):
    """
    Remove an installed app from the database.

    Args:
        db: Database connection
        app_id: App ID
        verbose: Whether to print verbose logs

    Returns:
        True if successful, False otherwise
    """
    try:
        await db.execute("DELETE FROM installed_apps WHERE id = ?", (app_id,))
        await db.commit()

        store_print(f"Removed app {app_id} from database", verbose)
        return True
    except Exception as e:
        store_print(f"Error removing app from database: {e}", verbose)
        return False

async def get_installed_apps(db, verbose=False):
    """
    Get list of installed apps from the database.

    Args:
        db: Database connection
        verbose: Whether to print verbose logs

    Returns:
        List of installed apps
    """
    installed_apps = []

    try:
        async with db.execute(
            "SELECT id, name, version, channel, architecture, install_date, app_dir FROM installed_apps"
        ) as cursor:
            async for row in cursor:
                app_id, name, version, channel, architecture, install_date, app_dir = row

                app_dir_exists = os.path.exists(app_dir) if app_dir else False

                if app_dir_exists:
                    app_info = {
                        'id': app_id,
                        'name': name,
                        'version': version,
                        'channel': channel,
                        'architecture': architecture,
                        'install_date': install_date,
                        'app_dir': app_dir
                    }
                    installed_apps.append(app_info)
                else:
                    await db.execute("DELETE FROM installed_apps WHERE id = ?", (app_id,))
                    await db.commit()
                    store_print(f"Removed {app_id} from database as app directory is missing", verbose)

        store_print(f"Found {len(installed_apps)} installed apps", verbose)
        return installed_apps
    except Exception as e:
        store_print(f"Error getting installed apps: {e}", verbose)
        return []

async def get_installed_app(db, app_id, verbose=False):
    """
    Get information about an installed app.

    Args:
        db: Database connection
        app_id: App ID
        verbose: Whether to print verbose logs

    Returns:
        App information or None if not found
    """
    try:
        async with db.execute(
            "SELECT id, name, version, channel, architecture, install_date, app_dir FROM installed_apps WHERE id = ?",
            (app_id,)
        ) as cursor:
            row = await cursor.fetchone()

            if row:
                app_id, name, version, channel, architecture, install_date, app_dir = row

                app_dir_exists = os.path.exists(app_dir) if app_dir else False

                if app_dir_exists:
                    app_info = {
                        'id': app_id,
                        'name': name,
                        'version': version,
                        'channel': channel,
                        'architecture': architecture,
                        'install_date': install_date,
                        'app_dir': app_dir
                    }
                    return app_info
                else:
                    await db.execute("DELETE FROM installed_apps WHERE id = ?", (app_id,))
                    await db.commit()
                    store_print(f"Removed {app_id} from database as app directory is missing", verbose)

            return None
    except Exception as e:
        store_print(f"Error getting installed app: {e}", verbose)
        return None
