    -- ──────────────────────────────────────────────────────────────
    -- Vacuum and Integrity Check Jobs
    -- ============================================================

    -- Run periodically:
    -- VACUUM ship_computer.db;
    -- VACUUM knowledge_base.db;
    -- ANALYZE ship_computer.db;
    -- ANALYZE knowledge_base.db;
* * *

🔄 Migration Strategy
---------------------

### **Phase 1: Backup & Planning**

python
    # Migration script outline
    import sqlite3
    import shutil
    import hashlib
    def migrate_databases():
        """Safe migration with full backup"""
        # 1. Full backup
        backup_path = f"{original_db}.backup.{int(time.time())}"
        shutil.copy(original_db, backup_path)

        # 2. Create new optimized database
        new_db = create_optimized_schema()

        # 3. Data migration with validation
        migrate_data_with_validation(original_db, new_db)

        # 4. Verify integrity
        verify_migration(original_db, new_db)

        # 5. Atomic swap with rollback capability
        atomic_swap_databases(original_db, new_db)

### **Phase 2: Incremental Migration**

* Migrate schema first
* Migrate data in batches
* Validate each batch
* Rollback on failure

* * *

📊 Expected Performance Improvements
------------------------------------

| Metric                | Before     | After        | Improvement             |
| --------------------- | ---------- | ------------ | ----------------------- |
| **Document Search**   | 2-5 sec    | < 50ms       | 40-50x faster           |
| **Settings Lookup**   | O(n)       | O(1)         | Instant                 |
| **Event Filtering**   | Slow       | Optimized    | 10-20x faster           |
| **Model Discovery**   | 1-3 sec    | < 100ms      | 30x faster              |
| **Database Size**     | Fragmented | Defragmented | ~20-30% smaller         |
| **Query Consistency** | Variable   | Optimized    | Predictable performance |

* * *

🛡️ Data Integrity & Safety
---------------------------

python
    # Safety mechanisms
    - Transaction wrapping for all writes
    - Checkpoint journaling (WAL mode)
    - Integrity checks before operations
    - Automatic backup before migrations
    - Rollback capability for failed migrations

* * *

📋 Implementation Checklist
---------------------------

*  Create new optimized schema files
*  Write migration scripts with validation
*  Test migration on development copy
*  Perform incremental migration on production
*  Verify data integrity post-migration
*  Update application to use new schema
*  Monitor performance improvements
*  Document schema changes for developers

* * *


