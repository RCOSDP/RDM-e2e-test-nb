"""WEKO metadata form utilities for E2E tests (2025 version).

This module provides utilities for filling and reading WEKO metadata forms.
Two distinct form types are supported:

- ProjectMetadataForm: Project-level metadata (funding, project name, etc.)
- FileMetadataForm: File/folder-level metadata (data title, description, creators, etc.)

Design principles:
- Each method performs exactly one action, no fallbacks
- If fallback is needed, caller handles it explicitly
- No .first/.last - use explicit indices
- No conditional branches that hide unexpected behavior
- Use actual label text as keys
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class FieldType(Enum):
    """Metadata field input types."""

    INPUT = "input"
    INPUT_DIRECT = "input_direct"
    TEXTAREA = "textarea"
    SELECT = "select"
    POWER_SELECT = "power_select"
    RADIO = "radio"
    TABLE = "table"
    NAME_TABLE = "name_table"


class ProjectMetadataForm:
    """Project metadata form (GRDM metadata registration page).

    Ember registries UI uses <label data-test-question-label> elements.
    Grouped fields (e.g. プログラム名) use a <strong> heading with sub-labels.
    """

    FIELDS: Dict[str, FieldType] = {
        "資金配分機関情報": FieldType.POWER_SELECT,
        "体系的番号におけるプログラム情報コード": FieldType.INPUT,
        "プログラム名 (日本語)": FieldType.INPUT,
        "Program name (English)": FieldType.INPUT,
        "体系的番号": FieldType.INPUT,
        "プロジェクト名 (日本語)": FieldType.INPUT,
        "Project name (English)": FieldType.INPUT,
        "プロジェクトの分野": FieldType.POWER_SELECT,
    }

    # Grouped fields: label -> (group heading text, sub-label text)
    _GROUPED: Dict[str, tuple] = {
        "プログラム名 (日本語)": ("プログラム名", "日本語"),
        "Program name (English)": ("プログラム名", "English"),
        "プロジェクト名 (日本語)": ("プロジェクト名", "日本語"),
        "Project name (English)": ("プロジェクト名", "English"),
    }

    # Fields requiring exact text node match to avoid ambiguity
    _EXACT_MATCH = {"体系的番号"}

    def __init__(self, page, parent_locator=None):
        self.page = page
        self._root = parent_locator or page

    def _get_locator(self, label: str, field_type: FieldType):
        if label in self._GROUPED:
            group, sub = self._GROUPED[label]
            base_xpath = (
                f"//strong[contains(., '{group}')]"
                f"/ancestor::div[1]"
                f"/following-sibling::label[contains(., '{sub}')][1]"
                f"/following-sibling::div[1]"
            )
            match field_type:
                case FieldType.INPUT:
                    return self._root.locator(f"{base_xpath}//input")
                case _:
                    return self._root.locator(base_xpath)

        if label in self._EXACT_MATCH:
            label_xpath = f"//label[@data-test-question-label and .//text()='{label}']"
        else:
            label_xpath = f"//label[@data-test-question-label and contains(., '{label}')]"
        match field_type:
            case FieldType.INPUT:
                return self._root.locator(
                    f'{label_xpath}/following-sibling::div[1]//input'
                )
            case FieldType.POWER_SELECT:
                return self._root.locator(
                    f'{label_xpath}/following-sibling::div[1]'
                )
            case _:
                raise ValueError(f"Unsupported field type: {field_type}")

    def get_locator(self, label: str):
        """Get the locator for a field."""
        field_type = self.FIELDS[label]
        return self._get_locator(label, field_type)

    async def fill(self, label: str, value: str) -> None:
        """Fill a field with a value."""
        field_type = self.FIELDS[label]
        locator = self._get_locator(label, field_type)

        match field_type:
            case FieldType.INPUT:
                await locator.clear()
                await locator.fill(value)
            case FieldType.POWER_SELECT:
                await locator.locator(".ember-power-select-trigger").click()
                option = self._root.locator(
                    f'//li[contains(@class, "ember-power-select-option") and contains(., "{value}")]'
                )
                await option.click()

    async def get(self, label: str) -> str:
        """Get the current value of a field."""
        field_type = self.FIELDS[label]
        locator = self._get_locator(label, field_type)

        match field_type:
            case FieldType.INPUT:
                return await locator.input_value()
            case FieldType.POWER_SELECT:
                return await locator.locator(".ember-power-select-selected-item").text_content()

    async def fill_power_select_by_search(self, label: str, value: str) -> None:
        """Fill a power-select by typing in search box (alternative to fill)."""
        field_type = self.FIELDS[label]
        locator = self._get_locator(label, field_type)
        await locator.locator(".ember-power-select-trigger").click()
        search = self._root.locator(".ember-power-select-search-input")
        await search.fill(value)
        await search.press("Enter")


class FileMetadataForm:
    """File/folder metadata form (metadata edit dialog).

    New UI uses div.form-group with label elements.
    Grouped fields use div.metadata-group with strong headings and sub-labels.
    """

    FIELDS: Dict[str, FieldType] = {
        # Basic info
        "ファイル種別": FieldType.RADIO,
        "データ No.": FieldType.INPUT,
        "データの名称 (日本語)": FieldType.INPUT,
        "Data title (English)": FieldType.INPUT,
        "論文表題 (日本語)": FieldType.INPUT,
        "Paper title (English)": FieldType.INPUT,
        "掲載日・掲載更新日": FieldType.INPUT_DIRECT,
        "データの説明 (日本語)": FieldType.TEXTAREA,
        "Description (English)": FieldType.TEXTAREA,
        # Classification
        "データの分野": FieldType.SELECT,
        "データ種別": FieldType.SELECT,
        "概略データ量": FieldType.INPUT,
        # License and policy
        "管理対象データの利活用・提供方針 (有償/無償)": FieldType.RADIO,
        "管理対象データの利活用・提供方針 (ライセンス)": FieldType.SELECT,
        "管理対象データの利活用・提供方針 (引用方法等・日本語)": FieldType.TEXTAREA,
        "Data utilization and provision policy (citation information, English)": FieldType.TEXTAREA,
        # Access
        "アクセス権": FieldType.SELECT,
        "公開予定日": FieldType.INPUT_DIRECT,
        # Repository
        "リポジトリ情報 (日本語)": FieldType.INPUT,
        "Repository information (English)": FieldType.INPUT,
        "リポジトリURL・DOIリンク": FieldType.INPUT,
        # Creators
        "データ作成者": FieldType.TABLE,
        "著者名": FieldType.TABLE,
        # Hosting institution
        "データ管理機関 (日本語)": FieldType.INPUT,
        "Hosting institution (English)": FieldType.INPUT,
        "データ管理機関コード": FieldType.INPUT,
        # Bibliographic specific fields
        "論文（出版社版）のDOI": FieldType.INPUT,
        "論文の種類": FieldType.SELECT,
        "掲載誌名 (日本語)": FieldType.INPUT,
        "Journal Name (English)": FieldType.INPUT,
        "発行年月": FieldType.INPUT,
        "巻": FieldType.INPUT,
        "号": FieldType.INPUT,
        "掲載ページ (開始)": FieldType.INPUT,
        "掲載ページ (終了)": FieldType.INPUT,
        "学術論文を掲載した「機関リポジトリ等の情報基盤」のDOI": FieldType.INPUT,
        # Data manager
        "データ管理者の種類": FieldType.RADIO,
        "データ管理者の e-Rad 研究者番号": FieldType.INPUT,
        "データ管理者 (日本語)": FieldType.NAME_TABLE,
        "Data manager (English)": FieldType.NAME_TABLE,
        "データ管理者の所属組織名 (日本語)": FieldType.INPUT,
        "Contact organization of data manager (English)": FieldType.INPUT,
        "データ管理者の所属機関の連絡先住所 (日本語)": FieldType.INPUT,
        "Contact address of data manager (English)": FieldType.INPUT,
        "データ管理者の所属機関の連絡先電話番号": FieldType.INPUT,
        "データ管理者の所属機関の連絡先メールアドレス": FieldType.INPUT,
        # Remarks
        "備考 (日本語)": FieldType.TEXTAREA,
        "Remarks (English)": FieldType.TEXTAREA,
        # Metadata access
        "メタデータのアクセス権": FieldType.SELECT,
        # Publication specific extra
        "査読の有無": FieldType.RADIO,
        "版情報": FieldType.SELECT,
    }

    # Grouped fields: label -> (group heading text, sub-label text)
    # Group heading is in <strong> inside .metadata-group-heading
    # Sub-label is in <label> inside .form-group within the group
    _GROUPED: Dict[str, tuple] = {
        "データの名称 (日本語)": ("データの名称", "（日本語）"),
        "Data title (English)": ("データの名称", "（English）"),
        "論文表題 (日本語)": ("論文表題", "（日本語）"),
        "Paper title (English)": ("論文表題", "（English）"),
        "データの説明 (日本語)": ("データの説明", "（日本語）"),
        "Description (English)": ("データの説明", "（English）"),
        "管理対象データの利活用・提供方針 (有償/無償)": ("管理対象データの利活用・提供方針", "有償/無償"),
        "管理対象データの利活用・提供方針 (ライセンス)": ("管理対象データの利活用・提供方針", "ライセンス"),
        "管理対象データの利活用・提供方針 (引用方法等・日本語)": ("引用方法等", "（日本語）"),
        "Data utilization and provision policy (citation information, English)": ("引用方法等", "（English）"),
        "リポジトリ情報 (日本語)": ("リポジトリ情報", "（日本語）"),
        "Repository information (English)": ("リポジトリ情報", "（English）"),
        "データ管理機関 (日本語)": ("データ管理機関", "（日本語）"),
        "Hosting institution (English)": ("データ管理機関", "（English）"),
        "データ管理者の e-Rad 研究者番号": ("データ管理者（個人）", "e-Rad研究者番号"),
        "データ管理者の所属組織名 (日本語)": ("データ管理者の所属組織名（①）", "（日本語）"),
        "Contact organization of data manager (English)": ("データ管理者の所属組織名（①）", "（English）"),
        "データ管理者の所属機関の連絡先住所 (日本語)": ("データ管理者の所属機関の連絡先住所（①）", "（日本語）"),
        "Contact address of data manager (English)": ("データ管理者の所属機関の連絡先住所（①）", "（English）"),
        "データ管理者の所属機関の連絡先電話番号": ("データ管理者の連絡先", "データ管理者の所属機関の連絡先電話番号"),
        "データ管理者の所属機関の連絡先メールアドレス": ("データ管理者の連絡先", "データ管理者の所属機関の連絡先メールアドレス"),
        "備考 (日本語)": ("備考", "（日本語）"),
        "Remarks (English)": ("備考", "（English）"),
        "掲載誌名 (日本語)": ("掲載誌名", "（日本語）"),
        "Journal Name (English)": ("掲載誌名", "（English）"),
        "掲載ページ (開始)": ("掲載ページ", "（開始）"),
        "掲載ページ (終了)": ("掲載ページ", "（終了）"),
    }

    # Name table fields: label -> (parent group heading, name sub-group heading, ja header, en header)
    # These are fields where a single-string input was replaced with a 姓/ミドルネーム/名 table.
    _NAME_TABLE_FIELDS: Dict[str, tuple] = {
        "データ管理者 (日本語)": ("データ管理者（個人）", "名前", "姓"),
        "Data manager (English)": ("データ管理者（個人）", "名前", "Last Name"),
    }

    def __init__(self, page, parent_locator=None):
        self.page = page
        self._root = parent_locator or page

    def _get_grouped_locator(self, label: str, field_type: FieldType):
        """Get locator for a field inside a metadata-group."""
        group, sub = self._GROUPED[label]
        # Find the group, then the sub-label's form-group within it
        group_xpath = (
            f"//*[contains(@class, 'metadata-group-heading') and contains(., '{group}')]"
            f"/parent::*[contains(@class, 'metadata-group')]"
        )
        label_xpath = f"//label[contains(text(), '{sub}')]"
        match field_type:
            case FieldType.INPUT:
                return self._root.locator(
                    f"{group_xpath}{label_xpath}/../following-sibling::div[1]//input"
                )
            case FieldType.TEXTAREA:
                return self._root.locator(
                    f"{group_xpath}{label_xpath}/../following-sibling::textarea[1]"
                )
            case FieldType.SELECT:
                return self._root.locator(
                    f"{group_xpath}{label_xpath}/../following-sibling::select[1]"
                )
            case FieldType.RADIO:
                return self._root.locator(
                    f"{group_xpath}{label_xpath}/../following-sibling::div[1]"
                )
            case _:
                return self._root.locator(
                    f"{group_xpath}{label_xpath}/.."
                )

    def _get_locator(self, label: str, field_type: FieldType):
        if label in self._GROUPED:
            return self._get_grouped_locator(label, field_type)

        exact_labels = {"号", "アクセス権"}
        if label in exact_labels:
            label_xpath = f'//label[normalize-space(.) = "{label}"]'
        else:
            label_xpath = f'//label[contains(text(), "{label}")]'

        match field_type:
            case FieldType.INPUT:
                return self._root.locator(
                    f'{label_xpath}/../following-sibling::div[1]//input'
                )
            case FieldType.INPUT_DIRECT:
                return self._root.locator(
                    f'{label_xpath}/../following-sibling::input[1]'
                )
            case FieldType.TEXTAREA:
                return self._root.locator(
                    f'{label_xpath}/../following-sibling::div[1]//textarea'
                )
            case FieldType.SELECT:
                return self._root.locator(
                    f'{label_xpath}/../following-sibling::select[1]'
                )
            case FieldType.RADIO:
                return self._root.locator(
                    f'{label_xpath}/../following-sibling::div[1]'
                )
            case FieldType.TABLE:
                return self._root.locator(
                    f'{label_xpath}/../following-sibling::div[1]'
                )
            case _:
                raise ValueError(f"Unsupported field type: {field_type}")

    def get_locator(self, label: str):
        """Get the locator for a field."""
        field_type = self.FIELDS[label]
        return self._get_locator(label, field_type)

    async def fill(self, label: str, value: str) -> None:
        """Fill a field with a value (not for TABLE type)."""
        field_type = self.FIELDS[label]
        locator = self._get_locator(label, field_type)

        match field_type:
            case FieldType.INPUT | FieldType.INPUT_DIRECT:
                await locator.clear()
                await locator.fill(value)
            case FieldType.TEXTAREA:
                await locator.clear()
                await locator.fill(value)
            case FieldType.SELECT:
                await locator.select_option(label=value)
            case FieldType.RADIO:
                await locator.locator(f'label:has-text("{value}") input[type="radio"]').click()
            case FieldType.TABLE:
                raise ValueError("Use table methods for TABLE type fields")
            case FieldType.NAME_TABLE:
                raise ValueError("Use fill_name for NAME_TABLE type fields")

    async def get(self, label: str) -> str:
        """Get the current value of a field (not for TABLE/NAME_TABLE type)."""
        field_type = self.FIELDS[label]
        locator = self._get_locator(label, field_type)

        match field_type:
            case FieldType.INPUT | FieldType.INPUT_DIRECT | FieldType.TEXTAREA:
                return await locator.input_value()
            case FieldType.SELECT:
                return await locator.input_value()
            case FieldType.RADIO:
                checked = locator.locator('input[type="radio"]:checked')
                if await checked.count() == 0:
                    return ''
                return await checked.input_value()
            case FieldType.TABLE:
                raise ValueError("Use table methods for TABLE type fields")
            case FieldType.NAME_TABLE:
                raise ValueError("Use get_name for NAME_TABLE type fields")

    def _get_any_locator(self, label: str):
        """Get a locator for any field type, including NAME_TABLE."""
        field_type = self.FIELDS[label]
        if field_type == FieldType.NAME_TABLE:
            return self._get_name_table_locator(label)
        return self._get_locator(label, field_type)

    def get_clear_checkbox(self, label: str):
        """Get the clear checkbox locator for a field (multiple-edit mode)."""
        locator = self._get_any_locator(label)
        form_group = locator.locator('xpath=ancestor::div[contains(@class, "form-group")][1]')
        return form_group.locator('input.metadata-form-clear-checkbox')

    async def expect_cleared(self, label: str, expect_fn, timeout: int) -> None:
        """Assert that a field is properly disabled after clear.

        Uses the appropriate assertion for each field type:
        - RADIO/NAME_TABLE: all inputs must be disabled (none remain enabled)
        - TABLE: "追加" link must have disabled class
        - Others: the field element itself must be disabled
        """
        import re
        field_type = self.FIELDS[label]
        locator = self._get_any_locator(label)
        match field_type:
            case FieldType.RADIO:
                await expect_fn(locator.locator('input[type="radio"]:not([disabled])')).to_have_count(0, timeout=timeout)
            case FieldType.TABLE:
                await expect_fn(locator.locator('xpath=.//a[span[text() = "追加"]]')).to_have_class(re.compile(r'.*disabled.*'), timeout=timeout)
            case FieldType.NAME_TABLE:
                await expect_fn(locator.locator('tbody td input:not([disabled])')).to_have_count(0, timeout=timeout)
            case _:
                await expect_fn(locator).to_be_disabled(timeout=timeout)

    async def scroll_to(self, label: str) -> None:
        """Scroll to make a field visible."""
        field_type = self.FIELDS[label]
        if field_type == FieldType.NAME_TABLE:
            locator = self._get_name_table_locator(label)
        else:
            locator = self._get_locator(label, field_type)
        await locator.scroll_into_view_if_needed()

    # Name table operations

    def _get_name_table_locator(self, label: str):
        """Get locator for a name table (姓/ミドルネーム/名) field."""
        parent_group, name_group, header = self._NAME_TABLE_FIELDS[label]
        # Navigate: parent group → name sub-group → table identified by column header
        return self._root.locator(
            f"//*[contains(@class, 'metadata-group-heading') and contains(., '{parent_group}')]"
            f"/parent::*[contains(@class, 'metadata-group')]"
            f"//*[contains(@class, 'metadata-group-heading') and contains(., '{name_group}')]"
            f"/parent::*[contains(@class, 'metadata-group')]"
            f"//table[.//th[text()='{header}']]"
        )

    async def _fill_name_table(self, table, name: Dict[str, str]) -> None:
        """Fill a 姓/ミドルネーム/名 table. Shared by fill_name and fill_author."""
        await table.locator('tbody td:nth-of-type(1) input').fill(name['last'])
        await table.locator('tbody td:nth-of-type(2) input').fill(name['middle'])
        await table.locator('tbody td:nth-of-type(3) input').fill(name['first'])

    async def _get_name_table(self, table) -> Dict[str, str]:
        """Read values from a 姓/ミドルネーム/名 table."""
        return {
            'last': await table.locator('tbody td:nth-of-type(1) input').input_value(),
            'middle': await table.locator('tbody td:nth-of-type(2) input').input_value(),
            'first': await table.locator('tbody td:nth-of-type(3) input').input_value(),
        }

    async def fill_name(self, label: str, name: Dict[str, str]) -> None:
        """Fill a name table field. name = {'last': ..., 'middle': ..., 'first': ...}"""
        table = self._get_name_table_locator(label)
        await self._fill_name_table(table, name)

    async def get_name(self, label: str) -> Dict[str, str]:
        """Get name table values. Returns {'last': ..., 'middle': ..., 'first': ...}"""
        table = self._get_name_table_locator(label)
        return await self._get_name_table(table)

    # Table operations

    async def get_table_row_count(self, label: str) -> int:
        """Get the number of rows in a table field."""
        locator = self._get_locator(label, FieldType.TABLE)
        return await locator.locator("table tbody tr").count()

    async def click_table_add_row(self, label: str) -> None:
        """Click the add row button in a table field."""
        locator = self._get_locator(label, FieldType.TABLE)
        await locator.locator("a:has(i.fa-plus)").click()

    async def click_table_remove_row(self, label: str, row_index: int) -> None:
        """Click the remove button for a specific row (0-indexed)."""
        locator = self._get_locator(label, FieldType.TABLE)
        row = locator.locator(f"table tbody tr:nth-of-type({row_index + 1})")
        await row.locator(".remove-row i, span.remove-row i").click()

    async def fill_table_cell(self, label: str, row_index: int, col_index: int, value: str) -> None:
        """Fill a specific cell in a table field (0-indexed)."""
        locator = self._get_locator(label, FieldType.TABLE)
        row = locator.locator(f"table tbody tr:nth-of-type({row_index + 1})")
        cell_input = row.locator(f"td:nth-of-type({col_index + 1}) input")
        await cell_input.fill(value)

    async def get_table_cell(self, label: str, row_index: int, col_index: int) -> str:
        """Get value from a specific cell in a table field (0-indexed)."""
        locator = self._get_locator(label, FieldType.TABLE)
        row = locator.locator(f"table tbody tr:nth-of-type({row_index + 1})")
        cell_input = row.locator(f"td:nth-of-type({col_index + 1}) input")
        return await cell_input.input_value()

    async def _find_name_table(self, panel, header_text: str):
        """Find a name table within a panel by its column header text."""
        return panel.locator(f'xpath=.//table[.//th[text()="{header_text}"]]')

    async def fill_author(self, author: Dict[str, Any], table_label: str = "著者名", add_row: bool = True) -> None:
        """Fill author/creator fields in edit panel.

        When add_row=False, fills the existing visible edit-mode panel
        (for tables with initial_rows > 0).
        """
        container = self.get_locator(table_label)
        if add_row:
            await self.click_table_add_row(table_label)

        panel = container.locator('.metadata-edit-mode >> visible=true').last
        await panel.wait_for(state="visible")

        # e-Rad number
        await panel.locator(
            'xpath=.//label[contains(text(), "e-Rad 研究者番号")]/following-sibling::div[1]//input'
        ).fill(author['number'])

        # Names: use shared _fill_name_table with table column headers
        ja_table = await self._find_name_table(panel, "姓")
        await self._fill_name_table(ja_table, author['name_ja'])

        en_table = await self._find_name_table(panel, "Last Name")
        await self._fill_name_table(en_table, author['name_en'])

        # Affiliations: find by strong heading "所属機関名"
        affil_section = panel.locator(
            'xpath=.//strong[contains(text(), "所属機関名")]/parent::*/following-sibling::div[1]'
        )
        await affil_section.locator(
            'xpath=.//label[contains(text(), "（日本語）")]/following-sibling::div[1]//input'
        ).fill(author['affiliation_ja'])
        await affil_section.locator(
            'xpath=.//label[contains(text(), "（English）")]/following-sibling::div[1]//input'
        ).fill(author['affiliation_en'])

        await panel.locator('.hide-edit-row').click()

    async def get_author(self, table_label: str = "著者名", row_index: int = 0) -> Dict[str, Any]:
        """Read author/creator data from a table row's edit panel."""
        container = self.get_locator(table_label)
        panel = container.locator('tr.metadata-edit-mode').nth(row_index)

        number = await panel.locator(
            'xpath=.//label[contains(text(), "e-Rad 研究者番号")]/following-sibling::div[1]//input'
        ).input_value()

        ja_table = await self._find_name_table(panel, "姓")
        name_ja = await self._get_name_table(ja_table)

        en_table = await self._find_name_table(panel, "Last Name")
        name_en = await self._get_name_table(en_table)

        affil_section = panel.locator(
            'xpath=.//strong[contains(text(), "所属機関名")]/parent::*/following-sibling::div[1]'
        )
        affiliation_ja = await affil_section.locator(
            'xpath=.//label[contains(text(), "（日本語）")]/following-sibling::div[1]//input'
        ).input_value()
        affiliation_en = await affil_section.locator(
            'xpath=.//label[contains(text(), "（English）")]/following-sibling::div[1]//input'
        ).input_value()

        return {
            'number': number,
            'name_ja': name_ja,
            'name_en': name_en,
            'affiliation_ja': affiliation_ja,
            'affiliation_en': affiliation_en,
        }
