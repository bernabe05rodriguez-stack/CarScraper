import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

from backend.db.models import AuctionListing


def export_listings_to_excel(listings: list[AuctionListing], stats: dict | None = None) -> io.BytesIO:
    """Generate an Excel file from auction listings."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Auction Results"

    # Header style
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center")
    thin_border = Border(
        left=Side(style="thin"),
        right=Side(style="thin"),
        top=Side(style="thin"),
        bottom=Side(style="thin"),
    )

    headers = [
        "Year", "Make", "Model", "Starting Bid", "Sold Price",
        "Auction Days", "Bids", "Times Listed", "Status", "Link"
    ]

    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # Data rows
    money_fmt = '#,##0'
    for row_idx, listing in enumerate(listings, 2):
        ws.cell(row=row_idx, column=1, value=listing.year)
        ws.cell(row=row_idx, column=2, value=listing.make)
        ws.cell(row=row_idx, column=3, value=listing.model)

        starting_cell = ws.cell(row=row_idx, column=4, value=listing.starting_bid)
        starting_cell.number_format = money_fmt

        sold_cell = ws.cell(row=row_idx, column=5, value=listing.sold_price)
        sold_cell.number_format = money_fmt

        ws.cell(row=row_idx, column=6, value=listing.auction_days)
        ws.cell(row=row_idx, column=7, value=listing.bid_count)
        ws.cell(row=row_idx, column=8, value=listing.times_listed)
        ws.cell(row=row_idx, column=9, value="Sold" if listing.is_sold else "Not Sold")

        # Hyperlink to listing
        if listing.url:
            link_cell = ws.cell(row=row_idx, column=10, value="View Listing")
            link_cell.hyperlink = listing.url
            link_cell.font = Font(color="0563C1", underline="single")

        # Alternate row shading
        if row_idx % 2 == 0:
            light_fill = PatternFill(start_color="F2F3F4", end_color="F2F3F4", fill_type="solid")
            for col in range(1, len(headers) + 1):
                ws.cell(row=row_idx, column=col).fill = light_fill

    # Column widths
    col_widths = [8, 12, 25, 14, 14, 13, 8, 13, 10, 15]
    for i, width in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = width

    # Stats sheet
    if stats:
        ws_stats = wb.create_sheet("Statistics")
        ws_stats.cell(row=1, column=1, value="Metric").font = Font(bold=True)
        ws_stats.cell(row=1, column=2, value="Value").font = Font(bold=True)
        for i, (key, value) in enumerate(stats.items(), 2):
            label = key.replace("_", " ").title()
            ws_stats.cell(row=i, column=1, value=label)
            ws_stats.cell(row=i, column=2, value=value)
        ws_stats.column_dimensions["A"].width = 25
        ws_stats.column_dimensions["B"].width = 15

    # Freeze header row
    ws.freeze_panes = "A2"

    # Auto-filter
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}1"

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output
