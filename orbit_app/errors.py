class AppError(Exception):
    def __init__(self, message, code=7):
        super().__init__(message)
        self.code = code
