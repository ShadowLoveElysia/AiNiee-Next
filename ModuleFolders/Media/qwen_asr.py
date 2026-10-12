"""Shared speech-language hints and local recognizer device selection."""


LANGUAGES = {'auto': None, 'zh': 'Chinese', 'en': 'English', 'ja': 'Japanese',
             'ko': 'Korean', 'yue': 'Cantonese'}


def recognition_device(requested, model, torch):
    if requested != 'auto':
        return requested
    if model == 'sensevoice':
        return 'cpu'
    if torch.cuda.is_available():
        return 'cuda:0'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'
