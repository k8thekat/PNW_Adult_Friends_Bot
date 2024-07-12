CREATE TABLE
    IF NOT EXISTS guilds (guild_id INTEGER UNIQUE NOT NULL) STRICT;

CREATE TABLE
    IF NOT EXISTS prefixes (
        guild_id INTEGER NOT NULL,
        prefix TEXT,
        FOREIGN KEY (guild_id) REFERENCES guilds (guild_id) ON DELETE CASCADE,
        UNIQUE (guild_id, prefix)
    ) STRICT;

-- Unique per guild settings.
CREATE TABLE
    IF NOT EXISTS settings (
        guild_id INTEGER NOT NULL,
        mod_role_id INTEGER DEFAULT 0,
        msg_timeout INTEGER DEFAULT 60,
        verified_role_id INTEGER DEFAULT 0,
        welcome_channel_id INTEGER DEFAULT 0,
        rules_message_id INTEGER DEFAULT 0,
        notification_channel_id INTEGER DEFAULT 0,
        flirting_channel_id INTEGER DEFAULT 0,
        personal_intros_channel_id INTEGER DEFAULT 0,
        roles_channel_id INTEGER DEFAULT 0,
        infraction_log_channel_id INTEGER DEFAULT 0,
        FOREIGN KEY (guild_id) REFERENCES guilds (guild_id) ON DELETE CASCADE
    ) STRICT;

CREATE TABLE
    IF NOT EXISTS infractions (
        id INTEGER PRIMARY KEY,
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        reason_msg_link TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (guild_id) REFERENCES guilds (guild_id) ON DELETE CASCADE,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE,
        UNIQUE (user_id, reason_msg_link)
    ) STRICT;

CREATE TABLE
    IF NOT EXISTS users (
        guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        verified INTEGER NOT NULL DEFAULT 0,
        last_active_at INTEGER NOT NULL,
        banned INTEGER NOT NULL DEFAULT 0,
        cleaned INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (guild_id) REFERENCES guilds (guild_id) ON DELETE CASCADE
    ) STRICT;

CREATE TABLE
    IF NOT EXISTS user_leaves (
        user_id INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    ) STRICT;

CREATE TABLE
    IF NOT EXISTS user_images (
        id INTEGER PRIMARY KEY,
        user_id INTEGER NOT NULL,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    ) STRICT;

CREATE TABLE
    IF NOT EXISTS role_embeds (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        guild_id INTEGER NOT NULL,
        channel_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        UNIQUE (guild_id, channel_id, message_id)
    ) STRICT;