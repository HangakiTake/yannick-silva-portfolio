"""Synthetic Cursos file in the client's column layout (fictional names, example.com addresses)."""
import sys
from datetime import datetime, time
from openpyxl import Workbook

HDR = ["Profesor/a", "Titulo", "Fecha inicio curso", "Fecha fin curso", "Hora inicio", "Hora de fin",
       "Periodico", "Festivos", "Asistentes", "Plataforma", "Texto"]
TXT = "Hi !  This is the link for your English classes.  If you have any questions, please contact us.     Demo School Team  "
ROWS = [
    ["Profe Demo 1", "English A2+ Grupo 3", "14-09-2026", "14-12-2026", time(9), time(10), "lunes y miércoles",
     datetime(2026, 10, 12), "alumnos.a2@example.com", "Teams", TXT],
    ["Profe Demo 2", "English B2 Grupo 2", "15-09-2026", "15-12-2026", time(8), time(9, 30), "Martes y jueves",
     "12-10-2026; 08-12-2026", "ana@example.com, luis@example.com", "Teams", None],
    ["Profe Demo 3", "English C1 Grupo 1   ", "16-09-2026", "16-12-2026", time(13), time(15), "Viernes",
     None, "c1.group@example.com", "Teams", None],
    ["Profe Demo 1", "Business English", datetime(2026, 11, 30), datetime(2027, 1, 29), "18.30", "20h",
     "lunes, miercoles y viernes", "21-12-2026 a 06-01-2027", "biz1@example.com;biz2@example.com", "teams", "Business English - evening group"],
    ["Profe Demo 2", "Intensivo noviembre", "02-11-2026", "13-11-2026", time(10), time(12), "lunes a jueves",
     None, "int@example.com", "Google Meet", None],
    ["Profe Demo 3", "Error: weekday typo", "14-09-2026", "14-12-2026", time(9), time(10), "Lunez y martes", None, "x@example.com", "Teams", None],
    ["Profe Demo 3", "Error: end before start", "14-12-2026", "14-09-2026", time(9), time(10), "lunes", None, "x@example.com", "Teams", None],
    ["Profe Demo 3", "Error: end time before start", "14-09-2026", "14-12-2026", time(11), time(10), "lunes", None, "x@example.com", "Teams", None],
    ["Profe Demo 3", "Error: bad email", "14-09-2026", "14-12-2026", time(9), time(10), "lunes", None, "ana@@example", "Teams", None],
    ["Profe Demo 3", "Error: platform", "14-09-2026", "14-12-2026", time(9), time(10), "lunes", None, "x@example.com", "Zoom", None],
    ["Profe Nuevo", "Error: unmapped teacher", "14-09-2026", "14-12-2026", time(9), time(10), "lunes", None, "x@example.com", "Teams", None],
    ["Profe Demo 3", None, "14-09-2026", "14-12-2026", time(9), time(10), "lunes", None, "x@example.com", "Teams", None],
]
TEACHERS = [("Profe Demo 1", "profe1@example.com"), ("Profe Demo 2", "profe2@example.com"), ("Profe Demo 3", "profe3@example.com")]


def make(path):
    wb = Workbook(); ws = wb.active; ws.title = "Cursos"; ws.append(HDR)
    for r in ROWS:
        ws.append(r)
    for _ in range(3):
        ws.append([None] * len(HDR))  # empty rows, like the client's file
    t = wb.create_sheet("Profesores"); t.append(["Profesor/a", "Buzon (email)"])
    for x in TEACHERS:
        t.append(x)
    wb.save(path)


if __name__ == "__main__":
    make(sys.argv[1] if len(sys.argv) > 1 else "samples/Cursos_demo.xlsx")
