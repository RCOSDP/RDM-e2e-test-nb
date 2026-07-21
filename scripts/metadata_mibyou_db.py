"""Mibyou DB (未病DB) metadata form utilities for E2E tests.

This module provides utilities for filling and reading Mibyou Database metadata forms.
The form has multiple collapsible sections for different file types:
- Measurement procedures and conditions (測定手順・条件等)
- Folder structure (フォルダ構成)
- Text files (テキストファイル)
- Excel files (エクセルファイル)
- Image files (画像ファイル)
- Any files (任意のファイル)

Design principles:
- Each method performs exactly one action
- No .first/.last - use explicit indices
- Use actual label text as keys
- Handle collapsible sections properly
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List
import time


class FieldType(Enum):
    """Metadata field input types."""

    INPUT = "input"
    INPUT_WITH_AUTO = "input_with_auto"  # Input with auto-fetch button
    TEXTAREA = "textarea"
    SELECT = "select"
    TABLE = "table"
    SECTION_TOGGLE = "section_toggle"  # Collapsible section toggle button


class FileMibyouDbMetadataForm:
    """Mibyou DB metadata form (未病DBのメタデータ登録).

    This form contains collapsible sections for different types of file metadata.
    Each section must be expanded before interacting with fields inside it.
    """

    # Measurement section fields (測定手順・条件等)
    MEASUREMENT_FIELDS: Dict[str, FieldType] = {
        "測定対象（日本語）": FieldType.TEXTAREA,
        "Object of measurement (English)": FieldType.TEXTAREA,
        "関連する器官名など": FieldType.INPUT,
        "データの種類（日本語）": FieldType.TEXTAREA,
        "Data type (English)": FieldType.TEXTAREA,
        "測定装置の分類（日本語）": FieldType.TEXTAREA,
        "Classification of measuring devices (English)": FieldType.TEXTAREA,
        "計測装置名": FieldType.TABLE,  # Table with 2 columns
        "手順": FieldType.TABLE,  # Table with 2 columns (procedure)
        "その他測定条件・手順に関するメタデータ項目": FieldType.TABLE,  # 4 columns
        "備考（日本語）": FieldType.TEXTAREA,
        "Remarks (English)": FieldType.TEXTAREA,
    }

    # Folder structure section (フォルダ構成)
    FOLDER_FIELDS: Dict[str, FieldType] = {
        "データ格納フォルダの説明": FieldType.TABLE,  # 4 columns
        "備考（日本語）": FieldType.TEXTAREA,
        "Remarks (English)": FieldType.TEXTAREA,
    }

    # Text file section (テキストファイル)
    TEXT_FILE_FIELDS: Dict[str, FieldType] = {
        "ファイル名テーブル": FieldType.TABLE,  # 2 columns (folder, filename)
        "説明（日本語）": FieldType.TEXTAREA,
        "Description (English)": FieldType.TEXTAREA,
        "行の説明": FieldType.TABLE,  # 6 columns
        "列の説明": FieldType.TABLE,  # 6 columns
        "データ前処理（日本語）": FieldType.TEXTAREA,
        "Data preprocessing (English)": FieldType.TEXTAREA,
        "経時的に測定したデータ": FieldType.SELECT,
        "行数": FieldType.INPUT_WITH_AUTO,
        "列数": FieldType.INPUT_WITH_AUTO,
        "同種のファイル概数": FieldType.INPUT,
        "区切り文字": FieldType.INPUT_WITH_AUTO,
        "文字コード": FieldType.INPUT_WITH_AUTO,
        "備考（日本語）": FieldType.TEXTAREA,
        "Remarks (English)": FieldType.TEXTAREA,
    }

    # Excel file section (エクセルファイル)
    EXCEL_FILE_FIELDS: Dict[str, FieldType] = {
        "ファイル名テーブル": FieldType.TABLE,
        "説明（日本語）": FieldType.TEXTAREA,
        "Description (English)": FieldType.TEXTAREA,
        "行の説明": FieldType.TABLE,
        "列の説明": FieldType.TABLE,
        "データ前処理（日本語）": FieldType.TEXTAREA,
        "Data Preprocessing (English)": FieldType.TEXTAREA,
        "経時的に測定したデータ": FieldType.SELECT,
        "行数": FieldType.INPUT_WITH_AUTO,
        "列数": FieldType.INPUT_WITH_AUTO,
        "同種のファイル概数": FieldType.INPUT,
        "備考（日本語）": FieldType.TEXTAREA,
        "Remarks (English)": FieldType.TEXTAREA,
    }

    # Image file section (画像ファイル)
    IMAGE_FILE_FIELDS: Dict[str, FieldType] = {
        "ファイル名テーブル": FieldType.TABLE,
        "説明（日本語）": FieldType.TEXTAREA,
        "Description (English)": FieldType.TEXTAREA,
        "データ前処理（日本語）": FieldType.TEXTAREA,
        "Data preprocessing (English)": FieldType.TEXTAREA,
        "経時的に測定したデータ": FieldType.SELECT,
        "幅ピクセル数": FieldType.INPUT_WITH_AUTO,
        "高さピクセル数": FieldType.INPUT_WITH_AUTO,
        "解像度（水平方向）": FieldType.INPUT_WITH_AUTO,
        "解像度（垂直方向）": FieldType.INPUT_WITH_AUTO,
        "色情報の数": FieldType.INPUT_WITH_AUTO,
        "色ビット数（色深度）": FieldType.INPUT,
        "圧縮形式": FieldType.INPUT,
        "同種のファイル概数": FieldType.INPUT,
        "画像タイプ": FieldType.INPUT_WITH_AUTO,
        "備考（日本語）": FieldType.TEXTAREA,
        "Remarks (English)": FieldType.TEXTAREA,
    }

    # Any file section (任意のファイル)
    ANY_FILE_FIELDS: Dict[str, FieldType] = {
        "ファイル名テーブル": FieldType.TABLE,
        "説明（日本語）": FieldType.TEXTAREA,
        "Description (English)": FieldType.TEXTAREA,
        "データ前処理（日本語）": FieldType.TEXTAREA,
        "Data Preprocessing (English)": FieldType.TEXTAREA,
        "経時的に測定したデータ": FieldType.SELECT,
        "行数": FieldType.INPUT_WITH_AUTO,
        "列数": FieldType.INPUT_WITH_AUTO,
        "同種のファイル概数": FieldType.INPUT,
        "テキスト/バイナリ": FieldType.SELECT,
        "画像タイプ": FieldType.INPUT_WITH_AUTO,
        "幅ピクセル数": FieldType.INPUT_WITH_AUTO,
        "高さピクセル数": FieldType.INPUT_WITH_AUTO,
        "解像度（水平方向）": FieldType.INPUT_WITH_AUTO,
        "解像度（垂直方向）": FieldType.INPUT_WITH_AUTO,
        "色情報の数": FieldType.INPUT_WITH_AUTO,
        "色ビット数（色深度）": FieldType.INPUT,
        "圧縮形式": FieldType.INPUT,
        "区切り文字": FieldType.INPUT_WITH_AUTO,
        "文字コード": FieldType.INPUT_WITH_AUTO,
        "ユーザー定義メタデータ項目": FieldType.TABLE,
        "備考（日本語）": FieldType.TEXTAREA,
        "Remarks (English)": FieldType.TEXTAREA,
    }

    def __init__(self, page, parent_locator=None):
        """Initialize the form with page and optional parent locator."""
        self.page = page
        self._root = parent_locator or page

    async def expand_section(self, section_name: str) -> None:
        """Expand a collapsible section by clicking its toggle button.

        Args:
            section_name: Name of section to expand. Options:
                - "測定手順・条件等" (Measurement)
                - "フォルダ構成" (Folder)
                - "テキストファイル" (Text)
                - "エクセルファイル" (Excel)
                - "画像ファイル" (Image)
                - "任意のファイル" (Any)
        """
        # Find the label with section name and click the toggle button
        section_label = self._root.locator(f'//label[contains(text(), "{section_name}")]')
        toggle_button = section_label.locator('../following-sibling::p//a[contains(text(), "項目を表示")]')

        # Check if section is already expanded by checking the concealment divs
        css_class = self._get_section_css_class(section_name)
        first_field = self._root.locator(f'.{css_class}').first

        # Check current height - if 0px then it's collapsed
        height = await first_field.evaluate('el => el.style.height')
        if height == '0px' or not height:
            await toggle_button.click()
            # Wait for animation to complete
            await self.page.wait_for_timeout(300)

    async def collapse_section(self, section_name: str) -> None:
        """Collapse a section by clicking its toggle button."""
        section_label = self._root.locator(f'//label[contains(text(), "{section_name}")]')
        toggle_button = section_label.locator('../following-sibling::p//a')

        css_class = self._get_section_css_class(section_name)
        first_field = self._root.locator(f'.{css_class}').first

        height = await first_field.evaluate('el => el.style.height')
        if height != '0px':
            await toggle_button.click()
            await self.page.wait_for_timeout(300)

    async def is_section_expanded(self, section_name: str) -> bool:
        """Check if a section is currently expanded.

        Args:
            section_name: Name of the section to check

        Returns:
            True if section is expanded, False if collapsed
        """
        css_class = self._get_section_css_class(section_name)
        first_field = self._root.locator(f'.{css_class}').first

        # Check if the field is visible and not hidden
        height = await first_field.evaluate('el => el.style.height')
        is_visible = await first_field.is_visible()

        # Section is expanded if height is not 0px and element is visible
        return height != '0px' and is_visible

    async def click_section_toggle(self, section_name: str) -> None:
        """Click the section toggle button (expand/collapse).

        This method simply clicks the toggle without checking current state.
        Use expand_section() or collapse_section() for specific actions.

        Args:
            section_name: Name of section
        """
        section_label = self._root.locator(f'//label[contains(text(), "{section_name}")]')
        toggle_button = section_label.locator('../following-sibling::p//a')
        await toggle_button.click()
        await self.page.wait_for_timeout(300)

    def _get_section_css_class(self, section_name: str) -> str:
        """Get the CSS class for a section's fields."""
        mapping = {
            "測定手順・条件等": "concealment-page-Label-measurement",
            "フォルダ構成": "concealment-page-Label-folder",
            "テキストファイル": "concealment-page-Label-text",
            "エクセルファイル": "concealment-page-Label-excel",
            "画像ファイル": "concealment-page-Label-image",
            "任意のファイル": "concealment-page-Label-any",
        }
        return mapping.get(section_name, "")

    def _get_locator(self, label: str, field_type: FieldType, section_css: str = None):
        """Get locator for a field within an optional section.

        Args:
            label: Field label text
            field_type: Type of field
            section_css: Optional CSS class to scope search to specific section
        """
        # Build base selector with optional section scope
        if section_css:
            base = f'//*[contains(@class, "{section_css}")]'
        else:
            base = '//*'

        label_xpath = f'{base}//label[contains(text(), "{label}")]'

        match field_type:
            case FieldType.INPUT:
                return self._root.locator(f'{label_xpath}/../following-sibling::div[1]//input')
            case FieldType.INPUT_WITH_AUTO:
                # Input field that has an auto-fetch button next to it
                return self._root.locator(
                    f'{label_xpath}/../following-sibling::div[1]//input[contains(@class, "form-control")]'
                )
            case FieldType.TEXTAREA:
                return self._root.locator(f'{label_xpath}/../following-sibling::textarea[1]')
            case FieldType.SELECT:
                return self._root.locator(f'{label_xpath}/../following-sibling::select[1]')
            case FieldType.TABLE:
                return self._root.locator(f'{label_xpath}/../following-sibling::div[1]')
            case _:
                raise ValueError(f"Unsupported field type: {field_type}")

    async def fill(self, section_name: str, label: str, value: str) -> None:
        """Fill a field value in a specific section.

        Args:
            section_name: Section name (e.g., "測定手順・条件等")
            label: Field label
            value: Value to fill
        """
        # Get section CSS and field type
        section_css = self._get_section_css_class(section_name)
        field_type = self._get_field_type(section_name, label)

        locator = self._get_locator(label, field_type, section_css)

        match field_type:
            case FieldType.INPUT | FieldType.INPUT_WITH_AUTO:
                await locator.clear()
                await locator.fill(value)
            case FieldType.TEXTAREA:
                await locator.clear()
                await locator.fill(value)
            case FieldType.SELECT:
                await locator.select_option(label=value)
            case FieldType.TABLE:
                raise ValueError("Use table methods for TABLE type fields")
        time.sleep(0.2)

    async def get(self, section_name: str, label: str) -> str:
        """Get field value from a specific section."""
        section_css = self._get_section_css_class(section_name)
        field_type = self._get_field_type(section_name, label)

        locator = self._get_locator(label, field_type, section_css)

        match field_type:
            case FieldType.INPUT | FieldType.INPUT_WITH_AUTO | FieldType.TEXTAREA:
                return await locator.input_value()
            case FieldType.SELECT:
                return await locator.locator("option:checked").text_content()
            case FieldType.TABLE:
                raise ValueError("Use table methods for TABLE type fields")

    def _get_field_type(self, section_name: str, label: str) -> FieldType:
        """Get the field type for a label in a section."""
        mapping = {
            "測定手順・条件等": self.MEASUREMENT_FIELDS,
            "フォルダ構成": self.FOLDER_FIELDS,
            "テキストファイル": self.TEXT_FILE_FIELDS,
            "エクセルファイル": self.EXCEL_FILE_FIELDS,
            "画像ファイル": self.IMAGE_FILE_FIELDS,
            "任意のファイル": self.ANY_FILE_FIELDS,
        }
        fields = mapping.get(section_name)
        if not fields:
            raise ValueError(f"Unknown section: {section_name}")
        if label not in fields:
            raise ValueError(f"Unknown field '{label}' in section '{section_name}'")
        return fields[label]

    async def get_table_row_count(self, section_name: str, label: str) -> int:
        """Get the number of rows in a table field."""
        section_css = self._get_section_css_class(section_name)

        locator = self._get_locator(label, FieldType.TABLE, section_css)
        return await locator.locator("table tbody tr").count()

    async def click_table_add_row(self, section_name: str, label: str) -> None:
        """Click the add row button in a table field."""
        section_css = self._get_section_css_class(section_name)

        locator = self._get_locator(label, FieldType.TABLE, section_css)
        await locator.locator("a:has(i.fa-plus)").click()

    async def click_table_remove_row(self, section_name: str, label: str, row_index: int) -> None:
        """Click the remove button for a specific row (0-indexed)."""
        section_css = self._get_section_css_class(section_name)

        locator = self._get_locator(label, FieldType.TABLE, section_css)
        row = locator.locator(f"table tbody tr:nth-of-type({row_index + 1})")
        await row.locator("span.remove-row i").click()

    async def fill_table_cell(
        self, section_name: str, label: str, row_index: int, col_index: int, value: str
    ) -> None:
        """Fill a specific cell in a table (0-indexed).

        For textarea cells, use this method.
        For input cells, use this method.
        """
        section_css = self._get_section_css_class(section_name)

        locator = self._get_locator(label, FieldType.TABLE, section_css)
        row = locator.locator(f"table tbody tr:nth-of-type({row_index + 1})")
        cell = row.locator(f"td:nth-of-type({col_index + 1})")

        # Try to find input first, then textarea
        input_field = cell.locator("input")
        if await input_field.count() > 0:
            await input_field.fill(value)
        else:
            textarea_field = cell.locator("textarea")
            await textarea_field.fill(value)
        time.sleep(0.2)

    async def get_table_cell(
        self, section_name: str, label: str, row_index: int, col_index: int
    ) -> str:
        """Get value from a specific cell in a table (0-indexed)."""
        section_css = self._get_section_css_class(section_name)

        locator = self._get_locator(label, FieldType.TABLE, section_css)
        row = locator.locator(f"table tbody tr:nth-of-type({row_index + 1})")
        cell = row.locator(f"td:nth-of-type({col_index + 1})")

        # Try input first, then textarea
        input_field = cell.locator("input")
        if await input_field.count() > 0:
            return await input_field.input_value()
        else:
            textarea_field = cell.locator("textarea")
            return await textarea_field.input_value()

    async def get_table_row_count_by_index(self, section_name: str, table_index: int) -> int:
        """Get the number of rows in a table by its index when label is empty.

        Args:
            section_name: Section name
            table_index: Index of table in section (0-indexed)

        Returns:
            Number of rows in the table
        """
        section_css = self._get_section_css_class(section_name)

        table = self._root.locator(f'//*[contains(@class, "{section_css}")]//table').nth(table_index)
        return await table.locator("tbody tr").count()

    async def click_table_add_row_by_index(self, section_name: str, table_index: int) -> None:
        """Click the add row button in a table by index (for empty labels).

        Args:
            section_name: Section name
            table_index: Index of table in section (0-indexed)
        """
        section_css = self._get_section_css_class(section_name)

        # Find the table, then get its parent container that has the add button
        table = self._root.locator(f'//*[contains(@class, "{section_css}")]//table').nth(table_index)
        container = table.locator('..')
        await container.locator("a:has(i.fa-plus)").click()

    async def fill_table_cell_by_index(
        self, section_name: str, table_index: int, row_index: int, col_index: int, value: str
    ) -> None:
        """Fill a specific cell in a table by table index (for empty labels).

        Use this method when the table label is empty or not available.

        Args:
            section_name: Section name
            table_index: Index of table in section (0-indexed)
            row_index: Row index (0-indexed)
            col_index: Column index (0-indexed)
            value: Value to fill
        """
        section_css = self._get_section_css_class(section_name)

        table = self._root.locator(f'//*[contains(@class, "{section_css}")]//table').nth(table_index)
        row = table.locator(f"tbody tr:nth-of-type({row_index + 1})")
        cell = row.locator(f"td:nth-of-type({col_index + 1})")

        # Try to find input first, then textarea
        input_field = cell.locator("input")
        if await input_field.count() > 0:
            await input_field.fill(value)
        else:
            textarea_field = cell.locator("textarea")
            await textarea_field.fill(value)
        time.sleep(0.2)

    async def get_table_cell_by_index(
        self, section_name: str, table_index: int, row_index: int, col_index: int
    ) -> str:
        """Get value from a specific cell by table index (for empty labels).

        Args:
            section_name: Section name
            table_index: Index of table in section (0-indexed)
            row_index: Row index (0-indexed)
            col_index: Column index (0-indexed)

        Returns:
            Cell value as string
        """
        section_css = self._get_section_css_class(section_name)

        table = self._root.locator(f'//*[contains(@class, "{section_css}")]//table').nth(table_index)
        row = table.locator(f"tbody tr:nth-of-type({row_index + 1})")
        cell = row.locator(f"td:nth-of-type({col_index + 1})")

        # Try input first, then textarea
        input_field = cell.locator("input")
        if await input_field.count() > 0:
            return await input_field.input_value()
        else:
            textarea_field = cell.locator("textarea")
            return await textarea_field.input_value()

    async def click_auto_fetch_button(self, section_name: str, label: str) -> None:
        """Click the auto-fetch button for fields with INPUT_WITH_AUTO type.

        Args:
            section_name: Section containing the field
            label: Field label (e.g., "行数", "列数", "文字コード")
        """
        section_css = self._get_section_css_class(section_name)

        # Find the input field, then locate the button next to it
        label_xpath = f'//*[contains(@class, "{section_css}")]//label[contains(text(), "{label}")]'
        button = self._root.locator(
            f'{label_xpath}/../following-sibling::div[1]//a[contains(@class, "btn")]/span[contains(text(), "自動取得")]/..'
        )
        await button.click()

        # Wait for the spinner to disappear (indicates completion)
        spinner = self._root.locator(
            f'{label_xpath}/../following-sibling::div[1]//i[contains(@class, "fa-spinner")]'
        )
        await spinner.wait_for(state="hidden", timeout=10000)

    async def batch_fill_fields(self, section: str, field_values: Dict[str, str]) -> None:
        """Fill multiple fields in a section efficiently.

        Args:
            section: Section name
            field_values: Dictionary of {field_label: value}
        """
        for label, value in field_values.items():
            await self.fill(section, label, value)

    async def batch_fill_table_row(
        self, section: str, table_label: str, row_index: int, values: List[str], use_index: bool = False
    ) -> None:
        """Fill an entire table row with values.

        Args:
            section: Section name
            table_label: Table label (or empty string if using index)
            row_index: Row index (0-based)
            values: List of values for each column
            use_index: If True, use fill_table_cell_by_index instead
        """
        for col_index, value in enumerate(values):
            if use_index:
                await self.fill_table_cell_by_index(section, 0, row_index, col_index, value)
            else:
                await self.fill_table_cell(section, table_label, row_index, col_index, value)

    async def batch_validate_fields(self, section: str, expected_values: Dict[str, str]) -> Dict[str, Any]:
        """Validate multiple fields by batching reads.

        Args:
            section: Section name
            expected_values: Dictionary of {field_label: expected_value}

        Returns:
            Dictionary of validation results
        """
        results = {}
        for label, expected in expected_values.items():
            actual = await self.get(section, label)
            results[label] = {
                'expected': expected,
                'actual': actual,
                'match': actual == expected
            }
            assert actual == expected, f"{label} should be '{expected}', got '{actual}'"
        return results

    async def validate_table_row(
        self, section: str, table_label: str, row_index: int, expected_values: List[str], use_index: bool = False
    ) -> bool:
        """Validate an entire table row.

        Args:
            section: Section name
            table_label: Table label (empty for index-based access)
            row_index: Row index (0-based)
            expected_values: List of expected values for each column
            use_index: If True, use get_table_cell_by_index

        Returns:
            True if all values match
        """
        for col_index, expected in enumerate(expected_values):
            if use_index:
                actual = await self.get_table_cell_by_index(section, 0, row_index, col_index)
            else:
                actual = await self.get_table_cell(section, table_label, row_index, col_index)
            assert actual == expected, f"Cell [{row_index}, {col_index}] should be '{expected}', got '{actual}'"
        return True

    async def auto_fetch_and_validate(
        self, section: str, field_expectations: Dict[str, str]
    ) -> Dict[str, Any]:
        """自動取得ボタンをクリックして値を検証する統合関数

        Auto-fetch and validate fields in one operation.

        Args:
            section: Section name
            field_expectations: Dictionary of {field_label: expected_value}

        Returns:
            Dictionary of validation results

        Example:
            await form.auto_fetch_and_validate("テキストファイル", {
                "行数": "101",
                "列数": "5",
                "区切り文字": "comma",
                "文字コード": "ascii"
            })
        """
        # 自動取得ボタンをクリック
        for field_label in field_expectations.keys():
            await self.click_auto_fetch_button(section, field_label)

        # 値を一括検証
        return await self.batch_validate_fields(section, field_expectations)