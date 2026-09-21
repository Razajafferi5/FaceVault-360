from fastapi import Request

def get_pipeline(request: Request):
    return request.app.state.pipeline

def get_recognition_service(request: Request):
    return request.app.state.recognition_service

def get_enrollment_service(request: Request):
    return request.app.state.enrollment_service

def get_camera_manager(request: Request):
    return request.app.state.camera

def get_vector_store(request: Request):
    return request.app.state.vector_store

def get_rtsp_manager(request: Request):
    return request.app.state.rtsp_manager

