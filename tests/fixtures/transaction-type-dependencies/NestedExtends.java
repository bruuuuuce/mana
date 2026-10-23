package fixture;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;
@Service class Entry {
    static class Helper extends Sink { static void work() {} }
    @Autowired Sink sink;
    public void run() { sink.required(); }
    public void use() { Helper.work(); }
}
