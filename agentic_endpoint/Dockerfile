FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt ${LAMBDA_TASK_ROOT}/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

COPY app.py agent_profiles.yaml hospital_agentic_rag_knowledge.txt ${LAMBDA_TASK_ROOT}/

CMD ["app.lambda_handler"]
