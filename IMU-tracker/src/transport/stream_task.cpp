#include "transport/stream_task.hpp"

#include "protocol/wire_codec.hpp"

namespace mocap::transport {

bool StreamTask::poll() {
  core::MotionSample sample{};
  if (!queue_.pop(sample)) return false;
  protocol::EncodedFrame frame{};
  if (!protocol::WireCodec::encodeRawSample(node_id_, sequence_++, sample, frame) ||
      !transport_.send(frame.bytes.data(), frame.size)) {
    health_.transportError();
    return false;
  }
  return true;
}

}  // namespace mocap::transport
