#include "../include/frame_tx_queue.h"
#include <deque>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>

static void check(bool value) {
  if (!value) throw std::runtime_error("frame FIFO invariant failed");
}

int main() {
  FrameTxQueue<2, 16> queue;
  const uint8_t a[] = "first\n", b[] = "second\n";
  check(queue.data() == nullptr && queue.remaining() == 0);
  check(!queue.enqueue(nullptr, 1) && !queue.enqueue(a, 0));
  check(!queue.enqueue(a, 17));
  check(queue.enqueue(a, 6));
  check(queue.consume(2));
  check(queue.enqueue(b, 7));
  check(!queue.enqueue(a, 6));
  check(std::string(reinterpret_cast<const char *>(queue.data()), queue.remaining()) == "rst\n");
  check(!queue.consume(5)); // An invalid send result cannot advance the FIFO.
  check(queue.consume(4));
  check(std::string(reinterpret_cast<const char *>(queue.data()), queue.remaining()) == "second\n");
  check(queue.enqueue(a, 6)); // Wrap the tail while a previous frame remains.
  check(queue.consume(7) && queue.consume(6));
  check(queue.remaining() == 0 && !queue.consume(1));
  check(queue.enqueue(a, 6) && queue.consume(3));
  queue.clear(); // A new TCP connection must not inherit an old partial line.
  check(queue.enqueue(b, 7));
  check(std::string(reinterpret_cast<const char *>(queue.data()), queue.remaining()) == "second\n");

  FrameTxQueue<4, 32> tested;
  std::deque<std::string> reference;
  std::mt19937 random(20261027);
  for (int step = 0; step < 10000; ++step) {
    const auto action = random() % 10;
    if (action < 5) {
      std::string frame(static_cast<size_t>(random() % 31 + 1), static_cast<char>('a' + random() % 26));
      const bool accepted = tested.enqueue(reinterpret_cast<const uint8_t *>(frame.data()), frame.size());
      check(accepted == (reference.size() < 4));
      if (accepted) reference.push_back(frame);
      // Changing the caller's buffer must not modify a queued frame.
      frame.assign(frame.size(), '?');
    } else if (action < 9 && !reference.empty()) {
      const size_t sent = static_cast<size_t>(random() % (reference.front().size() + 1));
      check(tested.consume(sent));
      reference.front().erase(0, sent);
      if (reference.front().empty()) reference.pop_front();
    } else if (action == 9) {
      tested.clear();
      reference.clear();
    }
    if (reference.empty()) {
      check(tested.data() == nullptr && tested.remaining() == 0);
    } else {
      check(std::string(reinterpret_cast<const char *>(tested.data()), tested.remaining()) == reference.front());
    }
  }
  std::cout << "PASS: partial sends, congestion, wraparound, reconnect isolation; 10000 FIFO transitions\n";
}
