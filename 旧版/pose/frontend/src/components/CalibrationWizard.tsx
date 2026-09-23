import { useEffect, useState } from "react";
import { startMountCalibration } from "../api/controlClient";

interface CalibrationWizardProps {
  readonly onlineNodes: number;
}

type CalibrationStage = "check" | "ready" | "countdown" | "capturing" | "done" | "error";

export const CalibrationWizard = ({ onlineNodes }: CalibrationWizardProps) => {
  const [stage, setStage] = useState<CalibrationStage>("check");
  const [countdown, setCountdown] = useState(3);
  const [error, setError] = useState("");

  useEffect(() => {
    if (stage !== "countdown") return;
    if (countdown <= 0) {
      setStage("capturing");
      void startMountCalibration()
        .then(() => setStage("done"))
        .catch((reason: unknown) => {
          setError(reason instanceof Error ? reason.message : String(reason));
          setStage("error");
        });
      return;
    }
    const timer = window.setTimeout(() => setCountdown((value) => value - 1), 1000);
    return () => window.clearTimeout(timer);
  }, [countdown, stage]);

  const begin = (): void => {
    setError("");
    setCountdown(3);
    setStage("countdown");
  };

  return (
    <section className="panel calibration-panel">
      <div className="panel-heading">
        <div>
          <span className="eyebrow">MOUNT CALIBRATION</span>
          <h2>佩戴标定</h2>
        </div>
        <span className="step-indicator">{onlineNodes}/14 节点</span>
      </div>
      {stage === "check" && (
        <>
          <p>先确认各设备已经固定在对应肢段，节点编号与列表一致。</p>
          <button className="button" type="button" onClick={() => setStage("ready")}>检查完成</button>
        </>
      )}
      {stage === "ready" && (
        <>
          <p>双脚与肩同宽，正视前方，双臂水平展开并保持 T-pose。</p>
          <p className="warning-text">胸部没有实体传感器，其姿态会作为虚拟骨段随骨盆生成。</p>
          <button className="button" type="button" disabled={onlineNodes < 14} onClick={begin}>
            {onlineNodes < 14 ? "等待全部节点" : "开始三秒倒计时"}
          </button>
        </>
      )}
      {stage === "countdown" && <div className="countdown" aria-live="polite">{countdown || "保持"}</div>}
      {stage === "capturing" && <p className="capture-state"><span className="pulse-dot" />正在采集多帧安装偏置，请保持不动……</p>}
      {stage === "done" && (
        <>
          <p className="success-text">佩戴标定已完成，新的安装偏置已由 Python Bridge 保存。</p>
          <button className="button button-secondary" type="button" onClick={() => setStage("ready")}>重新标定</button>
        </>
      )}
      {stage === "error" && (
        <>
          <p className="error-text">标定失败：{error}</p>
          <button className="button button-secondary" type="button" onClick={() => setStage("ready")}>重试</button>
        </>
      )}
    </section>
  );
};
