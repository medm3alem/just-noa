# -*- coding: utf-8 -*-
# Coller tout ce fichier dans une boite Python Choregraphe (Python 2.7).
import socket
import select
import threading
import json

class MyClass(GeneratedClass):
    def __init__(self):
        GeneratedClass.__init__(self)
        self.running = False
        self.server = None
        self.thread = None

    def onLoad(self):
        pass

    def onUnload(self):
        self.running = False
        if self.server is not None:
            try:
                self.server.close()
            except Exception:
                pass

    def onInput_onStart(self):
        if self.running:
            self.logger.info('Passerelle deja active')
            return
        self.running = True
        self.thread = threading.Thread(target=self.listen)
        self.thread.daemon = True
        self.thread.start()

    def listen(self):
        server = None
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', 8765))
            server.listen(10)
            server.setblocking(False)
            self.server = server
            self.logger.info('Just Nao pret : 127.0.0.1:8765')
            while self.running:
                ready, _, _ = select.select([server], [], [], 0.5)
                if not ready:
                    continue
                try:
                    client, addr = server.accept()
                except socket.error as e:
                    if getattr(e, 'errno', None) == 10035:
                        continue
                    if not self.running:
                        break
                    raise
                t = threading.Thread(target=self.handle, args=(client,))
                t.daemon = True
                t.start()
        except Exception as e:
            if self.running:
                self.logger.error('Serveur : %s' % e)
        finally:
            self.running = False
            if server is not None:
                try:
                    server.close()
                except Exception:
                    pass
            self.server = None
            self.logger.info('Passerelle arretee')

    def handle(self, client):
        try:
            client.setblocking(True)
            client.settimeout(120.0)
            chunks = []
            size = 0
            while True:
                part = client.recv(8192)
                if not part:
                    raise ValueError('Message incomplet')
                chunks.append(part)
                size += len(part)
                if size > 2 * 1024 * 1024:
                    raise ValueError('Message trop volumineux')
                if '\n' in part:
                    break
            request = json.loads(''.join(chunks).split('\n', 1)[0])
            result = self.dispatch(request)
            response = {'ok': True, 'result': result}
        except Exception as e:
            self.logger.error('Commande : %s' % e)
            response = {'ok': False, 'error': str(e)}
        try:
            client.sendall(json.dumps(response) + '\n')
        except Exception:
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass

    def dispatch(self, req):
        cmd = req.get('cmd')
        if cmd == 'ping':
            return 'pong'
        motion = self.session().service('ALMotion')
        if cmd == 'status':
            awake = bool(motion.robotIsWakeUp())
            try:
                posture = self.session().service('ALRobotPosture').getPosture()
            except Exception:
                posture = None
            return {'awake': awake, 'posture': posture}
        if cmd == 'wake':
            motion.wakeUp()
        elif cmd == 'rest':
            motion.rest()
        elif cmd == 'posture':
            ok = self.session().service('ALRobotPosture').goToPosture(
                req['posture'], float(req['speed']))
            if not ok:
                raise RuntimeError('Posture non atteinte')
        elif cmd == 'move':
            motion.angleInterpolation(req['names'], req['angles'],
                                      float(req['duration']), True)
        elif cmd == 'play':
            keys = req['keys']
            if keys and keys[0] and isinstance(keys[0][0], list):
                motion.angleInterpolationBezier(req['names'], req['times'], keys)
            else:
                motion.angleInterpolation(req['names'], keys, req['times'], True)
        elif cmd == 'stop':
            motion.killTasksUsingResources(req['names'])
        elif cmd == 'say':
            try:
                self.session().service('ALTextToSpeech').say(req['text'])
            except Exception as e:
                self.logger.info('Parole non disponible : %s' % e)
        elif cmd == 'stop_speech':
            try:
                self.session().service('ALTextToSpeech').stopAll()
            except Exception:
                pass
        elif cmd == 'leds':
            try:
                self.session().service('ALLeds').fadeRGB(
                    'FaceLeds', int(req['rgb']), float(req['duration']))
            except Exception as e:
                self.logger.info('LEDs non disponibles : %s' % e)
        else:
            raise ValueError('Commande inconnue : %s' % cmd)
        return 'OK'
