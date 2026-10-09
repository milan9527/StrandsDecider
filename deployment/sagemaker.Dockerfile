ARG MODEL_IMAGE
FROM ${MODEL_IMAGE}
USER root
COPY deployment/sagemaker_server.py /srv/sagemaker_server.py
EXPOSE 8080
ENTRYPOINT ["python", "/srv/sagemaker_server.py"]
CMD ["serve"]
