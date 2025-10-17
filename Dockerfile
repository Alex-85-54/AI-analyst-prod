FROM python:3.10

RUN apt-get -y update && apt-get -y upgrade && apt-get install build-essential

WORKDIR /app

COPY ./requirements.txt .

RUN pip install --upgrade pip
RUN pip install --upgrade pip setuptools
RUN python -m pip install -r requirements.txt

COPY . .

CMD ["python", "main.py"]