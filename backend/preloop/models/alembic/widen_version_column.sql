-- Pre-migration script to widen alembic_version.version_num
-- This handles the case where migration filenames exceed VARCHAR(32)
-- Run this ONCE before first `alembic upgrade head`

DO $$
BEGIN
    -- Check if table exists before trying to alter
    IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'alembic_version') THEN
        ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64);
        RAISE NOTICE 'Widened alembic_version.version_num to VARCHAR(64)';
    ELSE
        RAISE NOTICE 'alembic_version table does not exist yet - will be created with correct size';
    END IF;
END$$;
