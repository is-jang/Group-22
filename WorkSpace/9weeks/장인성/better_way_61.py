# 스레드를 사용한 I/O를 어떻게 asyncio로 포팅할 수 있는지 알아두라

import random
import contextlib
import math
import socket
from threading import Thread
import asyncio

WARMER = '더 따듯함'
COLDER = '더 차가움'
UNSURE = '잘 모르곘음'
CORRECT = '맞음'

class EOFError(Exception):
    pass

#class ConnectionBase:
class AsyncConnectionBase:
    def __init__(self, reader, writer):
        self.reader = reader
        self.writer = writer

    async def send(self, command): # async 추가
        line = command + '\n'
        data = line.encode()
        self.writer.write(data)
        await self.writer.drain()

    async def receive(self): # async 추가
        line = self.reader.readline()
        if not line:
            raise EOFError('연결 닫힘')
        return line[:-1].decode()


class UnknownCommandError(Exception):
    pass


#class Session(ConnectionBase):
class AsyncSession(AsyncConnectionBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._clear_state(None, None)

    def _clear_state(self, lower, upper):
        self.lower = lower
        self.upper = upper
        self.secret = None
        self.guesses = []


    async def loop(self):
        while command := await self.receive():
            parts = command.split(' ')
            if parts[0] == 'PARAMS':
                self.set_params(parts)
            elif parts[0] == 'NUMBER':
                await self.send_number()
            elif parts[0] == 'REPORT':
                self.receive_report(parts)
            else:
                raise UnknownCommandError(command)  
            
    def set_params(self, parts):
        assert len(parts) == 3
        lower = int(parts[1])
        upper = int(parts[2])
        self._clear_state(lower, upper)

    
    def next_guess(self):
        if self.secret is not None:
            return self.secret
        
        while True:
            guess = random.randint(self.lower, self.upper)
            if guess not in self.guesses:
                return guess
            
        
    async def send_number(self):
        guess = self.next_guess()
        self.guesses.append(guess)
        await self.send(format(guess))

    
    def receive_report(self, parts):
        assert len(parts) == 2
        decision = parts[1]

        last = self.guesses[-1]
        if decision == CORRECT:
            self.secret = last

        print(f'서버 {last}는 {decision}')


#class Client(ConnectionBase):
class AsyncClient(AsyncConnectionBase):
    def __init__(self, *args):
        super().__init__(*args)
        self._clear_state()

    def _clear_state(self):
        self.secret = None
        self.last_distance = None


    @contextlib.contextmanager
    async def session(self, lower, upper, secret):
        print(f"\n{lower}와 {upper} 사이의 숫자를 맞춰보세요!"f"쉿! 그 숫자는 {secret} 입니다.")
        self.secret = secret
        await self.send(f"PARAMS {lower} {upper}")
        try:
            yield
        finally:
            self._clear_state()
            await self.send('PARAMS 0 -1')

    async def request_numbers(self, count):
        for _ in range(count):
            await self.send("NUMBER")
            data = await self.receive()
            yield int(data)
            if self.last_distance == 0:
                return
            
    async def report_outcome(self, number):
        new_distance = math.fabs(number - self.secret)
        decision = UNSURE

        if new_distance == 0:
            decision = CORRECT
        elif self.last_distance is None:
            pass
        elif new_distance < self.last_distance:
            decision = WARMER
        elif new_distance > self.last_distance:
            decision = COLDER

        self.last_distance = new_distance

        await self.send(f"REPORT {decision}")
        return decision
    

async def handle_async_connection(connection):
    with connection:
        session = AsyncSession(connection)
        try:
            await session.loop()
        except EOFError:
            pass

async def run_async_server(address):
    server = await asyncio.start_server(
        handle_async_connection, *address
    )
    async with server:
        await server.serve_forever()

    
async def run_async_client(address):
    # with socket.create_connection(address) as connection:
    #     client = Client(connection)

    #     with client.session(1, 5, 3):
    #         results = [(x, client.report_outcome(x)) for x in client.request_numbers(5)]
        
    #     with client.session(10, 15, 12):
    #         for number in client.request_numbers(5):
    #             outcome = client.report_outcome(number)
    #             results.append((number, outcome))

    streams = await asyncio.open_connection(*address)
    client = AsyncClient(*streams)

    async with client.session(1, 5, 3):
        results = [(x, client.report_outcome(x)) async for x in client.request_numbers(5)]

    async with client.session(10, 15, 12):
        async for number in client.request_numbers(5):
            outcome = await client.report_outcome(number)
            results.append((number, outcome))

    _, writer = streams
    writer.close()
    await writer.wait_closed()
    
    return results


# def main():
async def main_async():
    address = ('127.0.0.1', 4321)
    # server_thread = Thread(target=run_server,
    #                        args=(address, ),
    #                        daemon=True)
    # server_thread.start()

    # results = run_client(address)
    # for number, outcome in results:
    #     print(f"클라이언트: {number}는 {outcome}")
    server = run_async_server(address)
    asyncio.create_task(server)

    results = await run_async_client(address)
    for number, outcome in results:
        print(f"클라이언트: {number}는 {outcome}")

asyncio.run(main_async())
