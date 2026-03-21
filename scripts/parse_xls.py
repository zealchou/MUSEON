import xlrd
import sys

fpath = sys.argv[1] if len(sys.argv) > 1 else "/Users/ZEALCHOU/MUSEON/data/uploads/telegram/20260321_115159_總工程估價單20240314(終價).xls"
wb = xlrd.open_workbook(fpath)

for sname in wb.sheet_names():
    print(f"=== Sheet: {sname} ===")
    sh = wb.sheet_by_name(sname)
    print(f"Rows: {sh.nrows}, Cols: {sh.ncols}")
    for r in range(min(sh.nrows, 300)):
        row = []
        for c in range(sh.ncols):
            v = sh.cell_value(r, c)
            if v != "":
                row.append(f"[{c}]{v}")
        if row:
            sep = " | "
            print(f"R{r}: {sep.join(row)}")
