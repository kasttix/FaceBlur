# Face Blur

Веб-приложение для размывания лиц или выбранных областей на видео.  
Поддерживает автоматическое определение лиц и ручное добавление масок прямо в браузере.

## Возможности
- Загрузка видео  
- Автоматическое распознавание лиц  
- Ручное добавление и редактирование масок  
- Регулировка силы размытия  
- Онлайн-превью результата  
- Сохранение обработанного видео  

## Системные требования
- Python 3.9+
- Docker  

## Установка и запуск
Установка локально:
python -m venv venv
source venv/bin/activate   # Linux / macOS
venv\Scripts\activate      # Windows
pip install -r requirements.txt
python app.py

Запуск в Docker:
docker build -t faceblur .
docker run -it --rm -p 9000:9000 -v $(pwd):/app faceblur

Запуск в Docker Compose:
docker-compose build
docker-compose up

Для остановки используйте сочетание клавиш Ctrl + C
## Используемые инструменты
Flask
OpenCV
NumPy
HTML / CSS / JavaScript
Docker

## Структура проекта
face-blur/
├── app.py          
├── requirements.txt   
├── Dockerfile    
├── docker-compose.yml
├── README.md          
├── static/          
│   ├── app.js
│   └── styles.css
├── templates/        
│   └── index.html
├── uploads/            # создаётся автоматически 
└── exports/            # создаётся автоматически 


