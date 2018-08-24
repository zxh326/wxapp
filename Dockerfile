<<<<<<< HEAD

# Python support can be specified down to the minor or micro version
# (e.g. 3.6 or 3.6.3).
# OS Support also exists for jessie & stretch (slim and full).
# See https://hub.docker.com/r/library/python/ for all supported Python
# tags from Docker Hub.
FROM python:alpine

# If you prefer miniconda:
#FROM continuumio/miniconda3

LABEL Name=wxapp Version=0.0.1
EXPOSE 8080

WORKDIR /app
ADD . /app

# Using pip:
RUN python3 -m pip install -r requirements.txt
CMD ["python3", "-m", "wxapp"]

# Using pipenv:
#RUN python3 -m pip install pipenv
#RUN pipenv install --ignore-pipfile
#CMD ["pipenv", "run", "python3", "-m", "wxapp"]

# Using miniconda (make sure to replace 'myenv' w/ your environment name):
#RUN conda env create -f environment.yml
#CMD /bin/bash -c "source activate myenv && python3 -m wxapp"
=======
FROM python:3.6
ENV PYTHONUNBUFFERED 1
RUN mkdir /webapps
WORKDIR /webapps

RUN apt-get update && apt-get upgrade -y && apt-get install -y \
libsqlite3-dev

COPY ./ /webapps/

RUN pip install -r /webapps/requirements.txt
>>>>>>> 0cae50d211a368a1078007c3c16fa1d848fc2c19