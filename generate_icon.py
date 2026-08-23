from PIL import Image, ImageDraw

size = 256
img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Fondo azul degradado usando rectángulos simples
for y in range(size):
    ratio = y / size
    r = int(30 + ratio * 40)
    g = int(88 + ratio * 60)
    b = int(210 + ratio * 30)
    draw.line((0, y, size, y), fill=(r, g, b, 255))

# Contenedor con fondo blanco
padding = 30
box = (padding, padding, size - padding, size - padding)
draw.rounded_rectangle(box, radius=42, fill=(255, 255, 255, 215))

# Símbolo de prompt
prompt_color = (30, 60, 150, 255)
# Círculo/órbita izquierda
left = (78, 86, 170, 178)
draw.ellipse(left, outline=prompt_color, width=18)
# Borde derecho
right = (120, 80, 214, 174)
draw.rounded_rectangle(right, radius=28, fill=prompt_color)
# Puntos y texto gui
for x, y in [(80, 196), (110, 196), (140, 196)]:
    draw.ellipse((x, y, x + 14, y + 14), fill=(255, 255, 255, 255))

# Letra M simplificada
m_x = 76
m_y = 82
points = [(m_x, 170), (m_x + 18, 86), (m_x + 38, 170), (m_x + 58, 86), (m_x + 78, 170)]
draw.line(points, fill=prompt_color, width=16)

img.save("app_icon.ico")
print("Icon generated: app_icon.ico")
