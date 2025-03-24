# SPDX-License-Identifier: GPL-2.0-only
# Copyright (C) 2025 Bardia Moshiri <bardia@furilabs.com>

import aiosqlite
import json
import os
from loguru import logger

async def init_app_database(db_path):
    """
    Initialize the app database.

    Args:
        db_path: Path to the database file

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
    logger.info("App database initialized")

    return db

async def init_installed_database(db_path):
    """
    Initialize the installed apps database.

    Args:
        db_path: Path to the database file

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
    logger.info("Installed apps database initialized")

    return db

async def save_app_list(db, apps):
    """
    Save a list of apps to the database.

    Args:
        db: Database connection
        apps: List of app dictionaries

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

        logger.info(f"Saved {len(apps)} apps to database")
        return True
    except Exception as e:
        logger.error(f"Error saving apps to database: {e}")
        return False

async def search_apps(db, query):
    """
    Search for apps in the database.

    Args:
        db: Database connection
        query: Search query

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

        logger.info(f"Found {len(results)} apps matching '{query}'")
        return results
    except Exception as e:
        logger.error(f"Error searching apps: {e}")
        return []

async def save_installed_app(db, app_id, name, version, channel, architecture,
                             install_date, app_dir):
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

        logger.info(f"Saved installed app {app_id} to database")
        return True
    except Exception as e:
        logger.error(f"Error saving installed app: {e}")
        return False

async def remove_installed_app(db, app_id):
    """
    Remove an installed app from the database.

    Args:
        db: Database connection
        app_id: App ID

    Returns:
        True if successful, False otherwise
    """
    try:
        await db.execute("DELETE FROM installed_apps WHERE id = ?", (app_id,))
        await db.commit()

        logger.info(f"Removed app {app_id} from database")
        return True
    except Exception as e:
        logger.error(f"Error removing app from database: {e}")
        return False

async def get_installed_apps(db):
    """
    Get list of installed apps from the database.

    Args:
        db: Database connection

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
                    logger.warning(f"Removed {app_id} from database as app directory is missing")

        logger.info(f"Found {len(installed_apps)} installed apps")
        return installed_apps
    except Exception as e:
        logger.error(f"Error getting installed apps: {e}")
        return []

async def get_installed_app(db, app_id):
    """
    Get information about an installed app.

    Args:
        db: Database connection
        app_id: App ID

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
                    logger.warning(f"Removed {app_id} from database as app directory is missing")

            return None
    except Exception as e:
        logger.error(f"Error getting installed app: {e}")
        return None
