package fixture;
class Result {}
public class Shadow {
    static class Result { Result() {} }
    public void run() { Result r = new Result(); }
}
