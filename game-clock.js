class Player {
  constructor(element, minutes = 1) {
    this.element = element;
    this.minutes = minutes;
    this.seconds = minutes * 60;
    this.interval = null;
  }

  startClock() {
    if (!this.interval) {
      this.interval = setInterval(() => this.tick(), 1000);
    }
  }

  stopClock() {
    clearInterval(this.interval);
    this.interval = null;
  }

  tick() {
    this.seconds--;
    this.updateClock();
    if (this.seconds <= 0) {
      this.stopClock();
    }
  }

  updateClock() {
    const minutes = Math.floor(this.seconds / 60);
    const seconds = this.seconds % 60;
    this.element.querySelector('.digit').textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
}

let currentPlayer = 1; // 1 = black, 2 = white
const blackPlayer = new Player(document.getElementById('black-clock'), 1);
const whitePlayer = new Player(document.getElementById('white-clock'), 1);

// Initialize clocks
blackPlayer.updateClock();
whitePlayer.updateClock();

document.getElementById('next-move-btn').addEventListener('click', function(){

    if(currentPlayer === 1) {
        blackPlayer.stopClock();
    } else {
        whitePlayer.stopClock();
    }

    socket.emit("updateClock", {
    match_id: match_id,
    player: currentPlayer,
    minutes: currentPlayer === 1 ? blackPlayer.minutes: whitePlayer.minutes,
    seconds: currentPlayer === 1 ? blackPlayer.seconds: whitePlayer.seconds
    })

    // 3. Switch turns
    currentPlayer = currentPlayer === 1 ? 2 : 1;

    if(currentPlayer === 1) {
        blackPlayer.startClock();
    } else {
        whitePlayer.startClock();
    }

    document.querySelectorAll('.player-turn').forEach(el => {
        el.classList.remove('active-turn');
    });

    document.getElementById(`player${currentPlayer}-turn`).classList.add('active-turn');
});
