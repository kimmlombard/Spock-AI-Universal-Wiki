"""Ship's Logs grid: rows must stay intact while the table is sorted.

Populating a QTableWidget with sorting live makes Qt re-sort after every
setItem(), which shuffles rows out from under the fill loop and leaves blank
cells with ids that look duplicated.
"""

import os
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from db_browser import DatabaseManager, TableBrowser
from spock_shell.theme import THEMES

ROWS = 60


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("grid") / "logs.db"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE documents (id INTEGER PRIMARY KEY, path TEXT, filename TEXT, "
        "file_size INTEGER)"
    )
    con.executemany(
        "INSERT INTO documents (id, path, filename, file_size) VALUES (?, ?, ?, ?)",
        [(i, f"D:\\repo\\file_{i}.py", f"file_{i}.py", i * 100) for i in range(1, ROWS + 1)],
    )
    con.commit()
    con.close()
    return str(path)


def _cells(browser, col):
    table = browser.table_widget
    return [
        table.item(r, col).text() if table.item(r, col) else "" for r in range(table.rowCount())
    ]


def test_every_row_is_populated_after_a_reload_while_sorted(app, db):
    browser = TableBrowser(DatabaseManager(db), "documents", THEMES["dark"])
    browser.table_widget.sortItems(0, Qt.SortOrder.DescendingOrder)
    browser.load_data()

    ids, paths = _cells(browser, 0), _cells(browser, 1)
    assert len(ids) == ROWS
    assert "" not in ids, "blank id cell — rows were shuffled during populate"
    assert "" not in paths, "blank path cell — rows were shuffled during populate"
    assert len(set(ids)) == ROWS, "duplicate ids in the grid"


def test_row_cells_stay_on_the_same_record(app, db):
    browser = TableBrowser(DatabaseManager(db), "documents", THEMES["dark"])
    browser.table_widget.sortItems(0, Qt.SortOrder.DescendingOrder)
    browser.load_data()

    for row in range(browser.table_widget.rowCount()):
        doc_id = browser.table_widget.item(row, 0).text()
        filename = browser.table_widget.item(row, 2).text()
        assert filename == f"file_{doc_id}.py"


def test_sorting_survives_a_reload_and_is_numeric(app, db):
    browser = TableBrowser(DatabaseManager(db), "documents", THEMES["dark"])
    assert browser.table_widget.isSortingEnabled()
    browser.table_widget.sortItems(0, Qt.SortOrder.DescendingOrder)
    browser.load_data()

    assert browser.table_widget.isSortingEnabled()
    ids = [int(v) for v in _cells(browser, 0)]
    # Text sorting would put 9 above 60; integer sort data keeps it numeric.
    assert ids == sorted(ids, reverse=True)
